from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    AmneziaWgClient,
    Node,
    Payment,
    Plan,
    PromoCode,
    PromoRedemption,
    Subscription,
    User,
    WalletTransaction,
    WireguardKey,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Repository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _commit_refresh(self, instance: Any) -> Any:
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def create_user(
        self,
        telegram_id: int,
        username: str | None = None,
        referrer_id: int | None = None,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            username=username,
            referrer_id=referrer_id,
            ref_code=f"tg{telegram_id}",
        )
        self.session.add(user)
        try:
            return await self._commit_refresh(user)
        except IntegrityError:
            await self.session.rollback()
            existing = await self.get_user_by_telegram_id(telegram_id)
            if existing is None:
                raise
            return existing

    async def get_or_create_user(self, telegram_id: int, username: str | None = None) -> User:
        user = await self.get_user_by_telegram_id(telegram_id)
        if user is not None:
            if user.username != username:
                user.username = username
                await self.session.commit()
                await self.session.refresh(user)
            return user
        return await self.create_user(telegram_id=telegram_id, username=username)

    async def get_user(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_user_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def list_users(self, limit: int = 100, offset: int = 0) -> list[User]:
        result = await self.session.execute(select(User).offset(offset).limit(limit).order_by(User.id))
        return list(result.scalars().all())

    async def update_user(self, user_id: int, **values: Any) -> User | None:
        user = await self.get_user(user_id)
        if user is None:
            return None
        for key, value in values.items():
            if hasattr(user, key):
                setattr(user, key, value)
        return await self._commit_refresh(user)

    async def delete_user(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        if user is None:
            return False
        await self.session.delete(user)
        await self.session.commit()
        return True

    async def create_subscription(
        self,
        user_id: int,
        plan: str,
        started_at: datetime,
        expires_at: datetime,
        is_active: bool = True,
        tier: str = "standard",
        panel_username: str | None = None,
        sub_token: str | None = None,
        subscription_url: str | None = None,
        traffic_limit_bytes: int | None = None,
        traffic_used_bytes: int = 0,
        device_limit: int | None = None,
        status: str = "active",
        node_ids: list[str] | None = None,
        static_ip: str | None = None,
        region: str | None = None,
    ) -> Subscription:
        subscription = Subscription(
            user_id=user_id,
            plan=plan,
            tier=tier,
            panel_username=panel_username,
            sub_token=sub_token,
            subscription_url=subscription_url,
            traffic_limit_bytes=traffic_limit_bytes,
            traffic_used_bytes=traffic_used_bytes,
            device_limit=device_limit,
            region=region,
            status=status,
            node_ids=node_ids,
            static_ip=static_ip,
            started_at=started_at,
            expires_at=expires_at,
            is_active=is_active,
        )
        self.session.add(subscription)
        return await self._commit_refresh(subscription)

    async def get_subscription(self, subscription_id: int) -> Subscription | None:
        return await self.session.get(Subscription, subscription_id)

    async def get_latest_subscription(self, user_id: int) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.expires_at.desc(), Subscription.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_active_subscription(self, user_id: int) -> Subscription | None:
        result = await self.session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.is_active.is_(True),
                Subscription.expires_at > _now(),
            )
            .order_by(Subscription.expires_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_active_subscriptions(self, user_id: int) -> list[Subscription]:
        """All currently-active subscriptions (one per tier after per-tier
        activation), newest expiry first."""
        result = await self.session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.is_active.is_(True),
                Subscription.expires_at > _now(),
            )
            .order_by(Subscription.tier, Subscription.expires_at.desc())
        )
        return list(result.scalars().all())

    async def get_latest_subscription_in_lane(self, user_id: int, premium: bool) -> Subscription | None:
        """Latest subscription in a billing lane. Premium (location-specific) and
        non-premium (trial + standard, main server) are independent lanes."""
        lane = Subscription.tier == "premium" if premium else Subscription.tier != "premium"
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id, lane)
            .order_by(Subscription.expires_at.desc(), Subscription.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_subscriptions_by_user(self, user_id: int) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc() if hasattr(Subscription, "created_at") else Subscription.id.desc())
        )
        return list(result.scalars().all())

    async def deactivate_user_subscriptions(self, user_id: int) -> None:
        await self.session.execute(
            update(Subscription)
            .where(Subscription.user_id == user_id, Subscription.is_active.is_(True))
            .values(is_active=False)
        )
        await self.session.commit()

    async def deactivate_subscriptions_in_lane(self, user_id: int, premium: bool) -> None:
        lane = Subscription.tier == "premium" if premium else Subscription.tier != "premium"
        await self.session.execute(
            update(Subscription)
            .where(Subscription.user_id == user_id, lane, Subscription.is_active.is_(True))
            .values(is_active=False)
        )
        await self.session.commit()

    async def deactivate_subscription(self, subscription_id: int) -> bool:
        subscription = await self.get_subscription(subscription_id)
        if subscription is None:
            return False
        subscription.is_active = False
        await self.session.commit()
        return True

    async def update_subscription(self, subscription_id: int, **values: Any) -> Subscription | None:
        subscription = await self.get_subscription(subscription_id)
        if subscription is None:
            return None
        for key, value in values.items():
            if hasattr(subscription, key):
                setattr(subscription, key, value)
        return await self._commit_refresh(subscription)

    async def list_active_panel_subscriptions(self) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(selectinload(Subscription.user))
            .where(
                Subscription.is_active.is_(True),
                Subscription.expires_at > _now(),
                Subscription.panel_username.is_not(None),
            )
            .order_by(Subscription.id)
        )
        return list(result.scalars().all())

    async def get_expiring_subscriptions(self, days: int = 3) -> list[Subscription]:
        now = _now()
        deadline = now + timedelta(days=days)
        result = await self.session.execute(
            select(Subscription)
            .options(selectinload(Subscription.user))
            .where(
                Subscription.is_active.is_(True),
                Subscription.expires_at > now,
                Subscription.expires_at <= deadline,
                Subscription.last_reminded_at.is_(None),
            )
            .order_by(Subscription.expires_at)
        )
        return list(result.scalars().all())

    async def get_expired_active_subscriptions(self) -> list[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(selectinload(Subscription.user))
            .where(
                Subscription.is_active.is_(True),
                Subscription.expires_at <= _now(),
            )
            .order_by(Subscription.expires_at)
        )
        return list(result.scalars().all())

    async def mark_subscription_reminded(self, subscription_id: int) -> None:
        await self.session.execute(
            update(Subscription)
            .where(Subscription.id == subscription_id)
            .values(last_reminded_at=_now())
        )
        await self.session.commit()

    async def delete_subscription(self, subscription_id: int) -> bool:
        result = await self.session.execute(delete(Subscription).where(Subscription.id == subscription_id))
        await self.session.commit()
        return result.rowcount > 0

    async def upsert_plan(
        self,
        code: str,
        title: str,
        tier: str,
        duration_days: int,
        price_rub: int,
        crypto_amount: str,
        traffic_limit_bytes: int | None,
        device_limit: int | None,
        description: str | None = None,
        is_active: bool = True,
        sort_order: int = 0,
    ) -> Plan:
        plan = await self.get_plan(code)
        if plan is None:
            plan = Plan(
                code=code,
                title=title,
                tier=tier,
                duration_days=duration_days,
                price_rub=price_rub,
                crypto_amount=crypto_amount,
                traffic_limit_bytes=traffic_limit_bytes,
                device_limit=device_limit,
                description=description,
                is_active=is_active,
                sort_order=sort_order,
            )
            self.session.add(plan)
            return await self._commit_refresh(plan)

        plan.title = title
        plan.tier = tier
        plan.duration_days = duration_days
        plan.price_rub = price_rub
        plan.crypto_amount = crypto_amount
        plan.traffic_limit_bytes = traffic_limit_bytes
        plan.device_limit = device_limit
        plan.description = description
        plan.is_active = is_active
        plan.sort_order = sort_order
        return await self._commit_refresh(plan)

    async def get_plan(self, code: str) -> Plan | None:
        return await self.session.get(Plan, code)

    async def list_plans(self, active_only: bool = True) -> list[Plan]:
        query = select(Plan).order_by(Plan.sort_order, Plan.code)
        if active_only:
            query = query.where(Plan.is_active.is_(True))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_node(
        self,
        tier: str,
        capacity: int,
        region: str,
        provider: str,
        ip_address: str,
        provider_instance_id: str | None = None,
        panel_node_id: str | None = None,
        current_users: int = 0,
        static_ips: list[str] | None = None,
        status: str = "active",
        name: str | None = None,
    ) -> Node:
        node = Node(
            name=name,
            tier=tier,
            capacity=capacity,
            region=region,
            provider=provider,
            provider_instance_id=provider_instance_id,
            ip_address=ip_address,
            panel_node_id=panel_node_id,
            current_users=current_users,
            static_ips=list(static_ips or []),
            status=status,
        )
        self.session.add(node)
        return await self._commit_refresh(node)

    async def get_node(self, node_id: int) -> Node | None:
        return await self.session.get(Node, node_id)

    async def get_node_by_panel_node_id(self, panel_node_id: str) -> Node | None:
        result = await self.session.execute(select(Node).where(Node.panel_node_id == panel_node_id))
        return result.scalar_one_or_none()

    async def get_node_by_provider_instance_id(self, provider_instance_id: str) -> Node | None:
        result = await self.session.execute(select(Node).where(Node.provider_instance_id == provider_instance_id))
        return result.scalar_one_or_none()

    async def list_nodes(
        self,
        tier: str | None = None,
        region: str | None = None,
        provider: str | None = None,
        status: str | None = None,
    ) -> list[Node]:
        query = select(Node).order_by(Node.id)
        if tier is not None:
            query = query.where(Node.tier == tier)
        if region is not None:
            query = query.where(Node.region == region)
        if provider is not None:
            query = query.where(Node.provider == provider)
        if status is not None:
            query = query.where(Node.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_available_nodes(
        self,
        tier: str,
        region: str | None = None,
        provider: str | None = None,
    ) -> list[Node]:
        query = (
            select(Node)
            .where(
                Node.tier == tier,
                Node.status == "active",
                Node.current_users < Node.capacity,
            )
            .order_by(Node.current_users, Node.capacity.desc(), Node.id)
        )
        if region is not None:
            query = query.where(Node.region == region)
        if provider is not None:
            query = query.where(Node.provider == provider)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_node(self, node_id: int, **values: Any) -> Node | None:
        node = await self.get_node(node_id)
        if node is None:
            return None
        for key, value in values.items():
            if hasattr(node, key):
                setattr(node, key, value)
        return await self._commit_refresh(node)

    async def delete_node(self, node_id: int) -> bool:
        node = await self.get_node(node_id)
        if node is None:
            return False
        await self.session.delete(node)
        await self.session.commit()
        return True

    async def create_wireguard_key(
        self,
        user_id: int,
        public_key: str,
        private_key: str,
        ip_address: str,
        config_file_path: str,
    ) -> WireguardKey:
        key = WireguardKey(
            user_id=user_id,
            public_key=public_key,
            private_key=private_key,
            ip_address=ip_address,
            config_file_path=config_file_path,
        )
        self.session.add(key)
        return await self._commit_refresh(key)

    async def get_wireguard_key(self, key_id: int) -> WireguardKey | None:
        return await self.session.get(WireguardKey, key_id)

    async def get_wireguard_key_by_user_id(self, user_id: int) -> WireguardKey | None:
        result = await self.session.execute(select(WireguardKey).where(WireguardKey.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_wireguard_key_by_public_key(self, public_key: str) -> WireguardKey | None:
        result = await self.session.execute(select(WireguardKey).where(WireguardKey.public_key == public_key))
        return result.scalar_one_or_none()

    async def get_all_wireguard_keys(self) -> list[WireguardKey]:
        result = await self.session.execute(select(WireguardKey).order_by(WireguardKey.id))
        return list(result.scalars().all())

    async def get_used_wireguard_ips(self) -> set[str]:
        result = await self.session.execute(select(WireguardKey.ip_address))
        return set(result.scalars().all())

    async def update_wireguard_key(self, key_id: int, **values: Any) -> WireguardKey | None:
        key = await self.get_wireguard_key(key_id)
        if key is None:
            return None
        for field, value in values.items():
            if hasattr(key, field):
                setattr(key, field, value)
        return await self._commit_refresh(key)

    async def delete_wireguard_key(self, key_id: int) -> bool:
        key = await self.get_wireguard_key(key_id)
        if key is None:
            return False
        await self.session.delete(key)
        await self.session.commit()
        return True

    async def get_amneziawg_client_by_user_id(self, user_id: int) -> AmneziaWgClient | None:
        result = await self.session.execute(
            select(AmneziaWgClient).where(AmneziaWgClient.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def next_amneziawg_ip_index(self) -> int:
        """Smallest free host index >= 2 (index 1 is the server on every node)."""
        result = await self.session.execute(select(AmneziaWgClient.ip_index))
        used = set(result.scalars().all())
        index = 2
        while index in used:
            index += 1
        return index

    async def create_amneziawg_client(
        self,
        user_id: int,
        public_key: str,
        private_key: str,
        ip_index: int,
    ) -> AmneziaWgClient:
        client = AmneziaWgClient(
            user_id=user_id,
            public_key=public_key,
            private_key=private_key,
            ip_index=ip_index,
        )
        self.session.add(client)
        return await self._commit_refresh(client)

    async def delete_amneziawg_client_by_user_id(self, user_id: int) -> bool:
        client = await self.get_amneziawg_client_by_user_id(user_id)
        if client is None:
            return False
        await self.session.delete(client)
        await self.session.commit()
        return True

    async def create_payment(
        self,
        user_id: int,
        amount: int,
        currency: str = "USDT",
        invoice_payload: str | None = None,
        status: str = "pending",
        telegram_payment_charge_id: str | None = None,
        provider_payment_charge_id: str | None = None,
    ) -> Payment:
        payment = Payment(
            user_id=user_id,
            amount=amount,
            currency=currency,
            invoice_payload=invoice_payload,
            status=status,
            telegram_payment_charge_id=telegram_payment_charge_id,
            provider_payment_charge_id=provider_payment_charge_id,
        )
        self.session.add(payment)
        return await self._commit_refresh(payment)

    async def create_cryptobot_payment(
        self,
        user_id: int,
        amount: int,
        external_invoice_id: str,
        invoice_payload: str,
        plan: str,
    ) -> Payment:
        payment = Payment(
            user_id=user_id,
            amount=amount,
            currency="USDT",
            provider="cryptobot",
            external_invoice_id=str(external_invoice_id),
            invoice_payload=invoice_payload,
            status="pending",
        )
        self.session.add(payment)
        return await self._commit_refresh(payment)

    async def get_payment(self, payment_id: int) -> Payment | None:
        return await self.session.get(Payment, payment_id)

    async def get_payment_by_payload(self, invoice_payload: str) -> Payment | None:
        result = await self.session.execute(select(Payment).where(Payment.invoice_payload == invoice_payload))
        return result.scalar_one_or_none()

    async def get_payment_by_external_id(self, external_invoice_id: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.external_invoice_id == str(external_invoice_id))
        )
        return result.scalar_one_or_none()

    async def list_payments_by_user(self, user_id: int) -> list[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.user_id == user_id).order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def complete_payment_by_payload(
        self,
        invoice_payload: str,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str | None = None,
    ) -> Payment | None:
        payment = await self.get_payment_by_payload(invoice_payload)
        if payment is None:
            return None
        payment.status = "completed"
        payment.telegram_payment_charge_id = telegram_payment_charge_id
        payment.provider_payment_charge_id = provider_payment_charge_id
        return await self._commit_refresh(payment)

    async def complete_payment_by_external_id(self, external_invoice_id: str) -> Payment | None:
        result = await self.session.execute(
            update(Payment)
            .where(
                Payment.external_invoice_id == str(external_invoice_id),
                Payment.provider == "cryptobot",
                Payment.status.in_(("pending", "processing")),
            )
            .values(
                status="completed",
                provider_payment_charge_id=str(external_invoice_id),
            )
            .returning(Payment.id)
        )
        payment_id = result.scalar_one_or_none()
        if payment_id is None:
            await self.session.rollback()
            return None

        await self.session.commit()
        return await self.get_payment(payment_id)

    async def claim_pending_cryptobot_payment(self, external_invoice_id: str) -> Payment | None:
        result = await self.session.execute(
            update(Payment)
            .where(
                Payment.external_invoice_id == str(external_invoice_id),
                Payment.provider == "cryptobot",
                Payment.status == "pending",
            )
            .values(status="processing")
            .returning(Payment.id)
        )
        payment_id = result.scalar_one_or_none()
        if payment_id is None:
            await self.session.rollback()
            return None

        await self.session.commit()
        return await self.get_payment(payment_id)

    async def update_payment_status(self, payment_id: int, status: str) -> Payment | None:
        payment = await self.get_payment(payment_id)
        if payment is None:
            return None
        payment.status = status
        return await self._commit_refresh(payment)

    async def delete_payment(self, payment_id: int) -> bool:
        payment = await self.get_payment(payment_id)
        if payment is None:
            return False
        await self.session.delete(payment)
        await self.session.commit()
        return True

    # ---- Wallet ledger -----------------------------------------------------

    async def get_balance(self, user_id: int) -> int | None:
        result = await self.session.execute(select(User.balance).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def credit_balance(
        self,
        user_id: int,
        amount: int,
        kind: str,
        reference: str | None = None,
        description: str | None = None,
    ) -> WalletTransaction | None:
        if amount <= 0:
            raise ValueError("credit amount must be positive")
        result = await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(balance=User.balance + amount)
            .returning(User.balance)
        )
        new_balance = result.scalar_one_or_none()
        if new_balance is None:
            # No row matched (unknown user); the UPDATE changed nothing, so there
            # is nothing to roll back. Avoid session.rollback() here because it
            # would expire the caller's loaded ORM objects.
            return None
        transaction = WalletTransaction(
            user_id=user_id,
            amount=amount,
            balance_after=new_balance,
            kind=kind,
            reference=reference,
            description=description,
        )
        self.session.add(transaction)
        return await self._commit_refresh(transaction)

    async def debit_balance(
        self,
        user_id: int,
        amount: int,
        kind: str,
        reference: str | None = None,
        description: str | None = None,
    ) -> WalletTransaction | None:
        if amount <= 0:
            raise ValueError("debit amount must be positive")
        result = await self.session.execute(
            update(User)
            .where(User.id == user_id, User.balance >= amount)
            .values(balance=User.balance - amount)
            .returning(User.balance)
        )
        new_balance = result.scalar_one_or_none()
        if new_balance is None:
            # No row matched (unknown user or insufficient balance); nothing was
            # changed, so skip rollback to keep the caller's identity map intact.
            return None
        transaction = WalletTransaction(
            user_id=user_id,
            amount=-amount,
            balance_after=new_balance,
            kind=kind,
            reference=reference,
            description=description,
        )
        self.session.add(transaction)
        return await self._commit_refresh(transaction)

    async def find_wallet_transaction(
        self,
        user_id: int,
        kind: str,
        reference: str,
    ) -> WalletTransaction | None:
        result = await self.session.execute(
            select(WalletTransaction).where(
                WalletTransaction.user_id == user_id,
                WalletTransaction.kind == kind,
                WalletTransaction.reference == reference,
            )
        )
        return result.scalars().first()

    async def list_wallet_transactions(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WalletTransaction]:
        result = await self.session.execute(
            select(WalletTransaction)
            .where(WalletTransaction.user_id == user_id)
            .order_by(WalletTransaction.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def sum_wallet_amount(self, user_id: int, kind: str | None = None) -> int:
        query = select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
            WalletTransaction.user_id == user_id
        )
        if kind is not None:
            query = query.where(WalletTransaction.kind == kind)
        result = await self.session.execute(query)
        return int(result.scalar_one())

    # ---- Admin aggregates --------------------------------------------------

    async def count_users(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(User))
        return int(result.scalar_one())

    async def count_users_since(self, since: datetime) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.created_at >= since)
        )
        return int(result.scalar_one())

    async def count_active_subscriptions_by_tier(self) -> dict[str, int]:
        result = await self.session.execute(
            select(Subscription.tier, func.count())
            .where(Subscription.is_active.is_(True), Subscription.expires_at > _now())
            .group_by(Subscription.tier)
        )
        return {str(tier): int(count) for tier, count in result.all()}

    async def sum_all_user_balances(self) -> int:
        result = await self.session.execute(select(func.coalesce(func.sum(User.balance), 0)))
        return int(result.scalar_one())

    async def sum_all_wallet_by_kind(self, kind: str) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
                WalletTransaction.kind == kind
            )
        )
        return int(result.scalar_one())

    async def count_subscriptions_total(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(Subscription))
        return int(result.scalar_one())

    async def recent_subscriptions(self, limit: int = 20) -> list[dict[str, Any]]:
        result = await self.session.execute(
            select(
                Subscription.id,
                Subscription.tier,
                Subscription.plan,
                Subscription.started_at,
                Subscription.expires_at,
                Subscription.is_active,
                User.telegram_id,
                User.username,
            )
            .join(User, User.id == Subscription.user_id)
            .order_by(Subscription.id.desc())
            .limit(limit)
        )
        return [
            {
                "id": row.id,
                "tier": row.tier,
                "plan": row.plan,
                "startedAt": row.started_at,
                "expiresAt": row.expires_at,
                "isActive": row.is_active,
                "telegramId": row.telegram_id,
                "username": row.username,
            }
            for row in result.all()
        ]

    # ---- Referrals ---------------------------------------------------------

    async def get_user_by_ref_code(self, ref_code: str) -> User | None:
        result = await self.session.execute(select(User).where(User.ref_code == ref_code))
        return result.scalar_one_or_none()

    async def count_referrals(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.referrer_id == user_id)
        )
        return int(result.scalar_one())

    async def list_referrals(self, user_id: int, limit: int = 100, offset: int = 0) -> list[User]:
        result = await self.session.execute(
            select(User)
            .where(User.referrer_id == user_id)
            .order_by(User.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    # ---- Promo codes -------------------------------------------------------

    async def create_promo_code(
        self,
        code: str,
        kind: str,
        value: int,
        min_amount_kopecks: int | None = None,
        max_uses: int | None = None,
        per_user_limit: int = 1,
        expires_at: datetime | None = None,
        is_active: bool = True,
        description: str | None = None,
    ) -> PromoCode:
        promo = PromoCode(
            code=code,
            kind=kind,
            value=value,
            min_amount_kopecks=min_amount_kopecks,
            max_uses=max_uses,
            per_user_limit=per_user_limit,
            is_active=is_active,
            description=description,
            expires_at=expires_at,
        )
        self.session.add(promo)
        return await self._commit_refresh(promo)

    async def get_promo_code(self, code: str) -> PromoCode | None:
        return await self.session.get(PromoCode, code)

    async def count_user_redemptions(self, code: str, user_id: int) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(PromoRedemption)
            .where(PromoRedemption.code == code, PromoRedemption.user_id == user_id)
        )
        return int(result.scalar_one())

    async def claim_promo_use(self, code: str) -> int | None:
        """Atomically bump ``used_count`` while respecting ``max_uses``.

        Returns the new ``used_count`` or ``None`` when the promo is inactive
        or already exhausted.
        """
        result = await self.session.execute(
            update(PromoCode)
            .where(
                PromoCode.code == code,
                PromoCode.is_active.is_(True),
                or_(PromoCode.max_uses.is_(None), PromoCode.used_count < PromoCode.max_uses),
            )
            .values(used_count=PromoCode.used_count + 1)
            .returning(PromoCode.used_count)
        )
        used_count = result.scalar_one_or_none()
        if used_count is None:
            # Promo inactive or exhausted: 0 rows changed, no rollback needed.
            return None
        await self.session.commit()
        return int(used_count)

    async def create_promo_redemption(
        self,
        code: str,
        user_id: int,
        applied_amount: int = 0,
        reference: str | None = None,
    ) -> PromoRedemption:
        redemption = PromoRedemption(
            code=code,
            user_id=user_id,
            applied_amount=applied_amount,
            reference=reference,
        )
        self.session.add(redemption)
        return await self._commit_refresh(redemption)
