from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    balance: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    lang: Mapped[str] = mapped_column(String(10), default="ru", server_default="ru", nullable=False)
    referrer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ref_code: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    wireguard_key: Mapped["WireguardKey | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    wallet_transactions: Mapped[list["WalletTransaction"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    referrer: Mapped["User | None"] = relationship(
        remote_side=[id],
        back_populates="referrals",
    )
    referrals: Mapped[list["User"]] = relationship(back_populates="referrer")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(50), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), default="standard", server_default="standard", index=True, nullable=False)
    panel_username: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    sub_token: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    subscription_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    traffic_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    traffic_used_bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    device_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", server_default="active", index=True, nullable=False)
    node_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    static_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="subscriptions")


class Plan(Base):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    price_rub: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    crypto_amount: Mapped[str] = mapped_column(String(32), nullable=False)
    traffic_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    device_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tier: Mapped[str] = mapped_column(String(32), default="premium", server_default="premium", index=True, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    region: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    provider_instance_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), unique=True, nullable=False)
    panel_node_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    current_users: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    static_ips: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", server_default="active", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )


class WireguardKey(Base):
    __tablename__ = "wireguard_keys"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_wireguard_keys_user_id"),
        UniqueConstraint("ip_address", name="uq_wireguard_keys_ip_address"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    public_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    private_key: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    config_file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="wireguard_key")


class AmneziaWgClient(Base):
    """One AmneziaWG identity per user, peered on every AWG node.

    The same keypair is registered on all nodes; ``ip_index`` is the shared host
    octet, so the per-node tunnel IP is the node subnet's network address + index
    (e.g. index 5 -> 10.13.13.5 on US, 10.13.14.5 on NL).
    """

    __tablename__ = "amneziawg_clients"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_amneziawg_clients_user_id"),
        UniqueConstraint("ip_index", name="uq_amneziawg_clients_ip_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    public_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    private_key: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_external_invoice_id", "external_invoice_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USDT", nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="cryptobot", server_default="cryptobot", nullable=False)
    external_invoice_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_payment_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_payload: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="payments")


class WalletTransaction(Base):
    """Append-only ledger of balance changes (kopecks, RUB minor units).

    Rows are never mutated after creation: every credit/debit appends a new
    entry carrying the signed ``amount`` and the resulting ``balance_after``.
    """

    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="wallet_transactions")


class PromoCode(Base):
    __tablename__ = "promo_codes"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    min_amount_kopecks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )

    redemptions: Mapped[list["PromoRedemption"]] = relationship(
        back_populates="promo",
        cascade="all, delete-orphan",
    )


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(ForeignKey("promo_codes.code", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    applied_amount: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )

    promo: Mapped[PromoCode] = relationship(back_populates="redemptions")
