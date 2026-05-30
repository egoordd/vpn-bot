from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Payment, Subscription, User, WireguardKey


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Repository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _commit_refresh(self, instance: Any) -> Any:
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def create_user(self, telegram_id: int, username: str | None = None) -> User:
        user = User(telegram_id=telegram_id, username=username)
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
    ) -> Subscription:
        subscription = Subscription(
            user_id=user_id,
            plan=plan,
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

    async def deactivate_subscription(self, subscription_id: int) -> bool:
        subscription = await self.get_subscription(subscription_id)
        if subscription is None:
            return False
        subscription.is_active = False
        await self.session.commit()
        return True

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
                Payment.status == "pending",
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
