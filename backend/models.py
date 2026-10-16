"""数据库模型定义。"""
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .util import now_local


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, onupdate=now_local
    )


class SchoolClass(Base, TimestampMixin):
    """班级（多班级管理的根实体）。

    - 宿舍 / 班费 / 定时提醒 / QQ 群绑定都挂在班级下
    - 启动时自动把没有班级的老数据归入「默认班级」
    """

    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), index=True, default="")
    note: Mapped[str] = mapped_column(String(300), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Dorm(Base, TimestampMixin):
    """宿舍。"""

    __tablename__ = "dorms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(Integer, default=0, index=True)  # 所属班级（0 = 未分配，启动时归入默认班级）
    room_no: Mapped[str] = mapped_column(String(40), index=True)  # 同一班级内唯一（不同班级可以重号）
    room_label: Mapped[str] = mapped_column(String(120), default="")  # 原始宿舍名称，如“新区校区6号学生公寓207”
    building: Mapped[str] = mapped_column(String(60), default="")
    leader_name: Mapped[str] = mapped_column(String(60), default="")
    leader_phone: Mapped[str] = mapped_column(String(40), default="")
    qq_group_id: Mapped[str] = mapped_column(String(40), default="")  # 该宿舍所在 QQ 群
    password_hash: Mapped[str] = mapped_column(String(200), default="")  # 兼容旧字段
    leader_password: Mapped[str] = mapped_column(String(200), default="")  # 寝室长验证密码（哈希）
    note: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    members: Mapped[list["Member"]] = relationship(
        back_populates="dorm", cascade="all, delete-orphan", order_by="Member.id"
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="dorm", cascade="all, delete-orphan"
    )

    @property
    def label(self) -> str:
        """界面上显示的完整宿舍名。"""
        if self.room_label:
            return self.room_label
        return f"{self.building}{self.room_no}" if self.building else self.room_no


class Member(Base, TimestampMixin):
    """宿舍成员。"""

    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dorm_id: Mapped[int] = mapped_column(ForeignKey("dorms.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60), index=True)
    student_no: Mapped[str] = mapped_column(String(60), default="", index=True)
    phone: Mapped[str] = mapped_column(String(40), default="")
    room_no: Mapped[str] = mapped_column(String(40), default="")  # 冗余保存，方便导出
    role: Mapped[str] = mapped_column(String(20), default="成员")  # 成员 / 宿舍长
    note: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    dorm: Mapped[Dorm] = relationship(back_populates="members")


class Report(Base):
    """每日填报记录（一个宿舍一天一条）。"""

    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("dorm_id", "report_date", name="uq_report_dorm_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dorm_id: Mapped[int] = mapped_column(ForeignKey("dorms.id", ondelete="CASCADE"), index=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)

    is_complete: Mapped[bool] = mapped_column(Boolean, default=True)  # 人员是否齐全
    absent_names: Mapped[str] = mapped_column(String(300), default="")  # 不在人员
    note: Mapped[str] = mapped_column(Text, default="")  # 备注（意外问题等）
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    present_count: Mapped[int] = mapped_column(Integer, default=0)
    absent_count: Mapped[int] = mapped_column(Integer, default=0)

    source: Mapped[str] = mapped_column(String(20), default="web")  # web / qq / qqbot / admin
    raw_message: Mapped[str] = mapped_column(Text, default="")  # QQ 群原始消息

    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, onupdate=now_local
    )
    submitter: Mapped[str] = mapped_column(String(60), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")  # 填写来源 IP
    user_agent: Mapped[str] = mapped_column(String(300), default="")  # 填写设备

    dorm: Mapped[Dorm] = relationship(back_populates="reports")
    checks: Mapped[list["ReportCheckin"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class ReportCheckin(Base):
    """某次填报里每个成员是否在寝。"""

    __tablename__ = "report_checkins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    member_id: Mapped[int] = mapped_column(Integer, default=0)
    member_name: Mapped[str] = mapped_column(String(60), default="")
    student_no: Mapped[str] = mapped_column(String(60), default="")
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str] = mapped_column(String(200), default="")

    report: Mapped[Report] = relationship(back_populates="checks")


class Account(Base, TimestampMixin):
    """登录账号。

    - role = admin  ：管理员，用用户名 + 密码登录管理端口，能管理全部数据
    - role = leader ：寝室长，用户名就是宿舍号（如 6-213），只能操作自己寝室
    """

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(60), default="")
    password_hash: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(20), default="admin", index=True)  # admin / leader
    dorm_id: Mapped[int] = mapped_column(Integer, default=0, index=True)  # 寝室长绑定的寝室
    phone: Mapped[str] = mapped_column(String(40), default="")
    note: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)  # 超级管理员，不可被删除
    must_change: Mapped[bool] = mapped_column(Boolean, default=False)  # 首次登录建议改密码
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_ip: Mapped[str] = mapped_column(String(64), default="")
    last_login_device: Mapped[str] = mapped_column(String(300), default="")


class FundSetting(Base, TimestampMixin):
    """班费基本设置（一条记录）。"""

    __tablename__ = "fund_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(Integer, default=0, index=True)  # 所属班级（每班一条）
    per_person: Mapped[float] = mapped_column(Float, default=50.0)  # 每人班费
    headcount: Mapped[int] = mapped_column(Integer, default=0)  # 人数
    total_fund: Mapped[float] = mapped_column(Float, default=0.0)  # 班费合计（留空则按 每人×人数）
    extra_in: Mapped[float] = mapped_column(Float, default=0.0)  # 后续补收 / 其他收入
    class_name: Mapped[str] = mapped_column(String(80), default="")
    note: Mapped[str] = mapped_column(String(300), default="")
    qq_group_id: Mapped[str] = mapped_column(String(40), default="")  # 班费汇报发到哪个群
    template: Mapped[str] = mapped_column(Text, default="")  # 汇报模板


class FundEntry(Base, TimestampMixin):
    """班费收支明细。"""

    __tablename__ = "fund_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(Integer, default=0, index=True)  # 所属班级
    seq: Mapped[int] = mapped_column(Integer, default=0, index=True)  # 序号
    entry_date: Mapped[date | None] = mapped_column(Date, index=True)  # 日期
    date_text: Mapped[str] = mapped_column(String(40), default="")  # 原样保留，兼容 2025.9.5 这类写法
    item: Mapped[str] = mapped_column(String(200), default="")  # 支出项目
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # 单价
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)  # 数量
    amount: Mapped[float] = mapped_column(Float, default=0.0, index=True)  # 金额
    direction: Mapped[str] = mapped_column(String(10), default="expense")  # expense 支出 / income 收入
    handler: Mapped[str] = mapped_column(String(80), default="")  # 经手人
    checker: Mapped[str] = mapped_column(String(80), default="")  # 核对人
    note: Mapped[str] = mapped_column(String(300), default="")  # 备注
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual / import
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 上次发群时间


class BotGroup(Base, TimestampMixin):
    """机器人收到过消息的群（QQ 官方机器人）。

    官方机器人发消息要用 group_openid，而 openid 只能从「群里 @ 机器人」后的事件里拿到，
    所以收到一次就存下来，控制台直接给管理员选。
    """

    __tablename__ = "bot_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(20), default="qqbot", index=True)
    class_id: Mapped[int] = mapped_column(Integer, default=0, index=True)  # 绑定的班级（0 = 未绑定，推送时回退全局群）
    group_openid: Mapped[str] = mapped_column(String(120), default="", index=True)
    group_no: Mapped[str] = mapped_column(String(40), default="")
    name: Mapped[str] = mapped_column(String(120), default="")
    last_user: Mapped[str] = mapped_column(String(120), default="")
    last_message: Mapped[str] = mapped_column(String(300), default="")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Setting(Base, TimestampMixin):
    """键值配置（机器人、定时任务、模板等全部在这里，可图形化修改）。"""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    group: Mapped[str] = mapped_column(String(40), default="general")
    description: Mapped[str] = mapped_column(String(200), default="")


class PushLog(Base):
    """消息推送日志（QQ 群汇报 / 定时提醒）。"""

    __tablename__ = "push_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    class_id: Mapped[int] = mapped_column(Integer, default=0, index=True)  # 所属班级（0 = 全局/历史）
    channel: Mapped[str] = mapped_column(String(20), index=True)  # qqbot / none（历史日志可能有 smtp / onebot / showdoc）
    scene: Mapped[str] = mapped_column(String(30), default="")  # daily_report / missing_reminder / test
    target: Mapped[str] = mapped_column(String(120), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="success")  # success / failed
    detail: Mapped[str] = mapped_column(Text, default="")
    trigger: Mapped[str] = mapped_column(String(20), default="auto")  # auto / manual
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)


class AuditLog(Base):
    """操作审计。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(60), default="")
    role: Mapped[str] = mapped_column(String(20), default="")
    action: Mapped[str] = mapped_column(String(80), default="")
    target: Mapped[str] = mapped_column(String(120), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")  # 操作设备（浏览器/手机）
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local, index=True)
