from sqlalchemy import Boolean, Column, Integer, String, Text, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database import Base

# 1. 一级领域表
class SysDomain(Base):
    __tablename__ = "sys_domains"
    d_id = Column(Integer, primary_key=True, index=True)
    d_name = Column(String(50), unique=True, nullable=False)
    d_desc = Column(Text, nullable=True)
    objects = relationship("SysObject", back_populates="domain")

# 2. 二级对象表
class SysObject(Base):
    __tablename__ = "sys_objects"
    o_id = Column(Integer, primary_key=True, index=True)
    d_id = Column(Integer, ForeignKey("sys_domains.d_id"))
    o_name = Column(String(50), nullable=False)
    o_desc = Column(Text, nullable=True)
    domain = relationship("SysDomain", back_populates="objects")
    effects = relationship("SysEffect", back_populates="object_")

# 3. 三级效果表
class SysEffect(Base):
    __tablename__ = "sys_effects"
    e_id = Column(Integer, primary_key=True, index=True)
    o_id = Column(Integer, ForeignKey("sys_objects.o_id"))
    e_name = Column(String(50), nullable=False)
    e_desc = Column(Text, nullable=True)
    object_ = relationship("SysObject", back_populates="effects")

# 4. 设备族类参考规约（环境匹配提示词；不定最终 a_ref）
PACK_KIND_UNIVERSAL = "universal"
PACK_KIND_FAMILY = "family"
PACK_KIND_GENERIC = "generic"
PACK_KINDS = {PACK_KIND_UNIVERSAL, PACK_KIND_FAMILY, PACK_KIND_GENERIC}


class DeviceGuidancePack(Base):
    __tablename__ = "device_guidance_packs"
    __table_args__ = (
        CheckConstraint(
            "pack_kind IN ('universal', 'family', 'generic')",
            name="ck_device_guidance_packs_kind",
        ),
    )

    pack_id = Column(String(32), primary_key=True)
    pack_kind = Column(String(16), nullable=False, index=True)
    display_name = Column(String(50), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    body_text = Column(Text, nullable=False, default="", server_default="")
    intent = Column(Text, nullable=False, default="", server_default="")
    function_map = Column(Text, nullable=False, default="", server_default="")
    forbid = Column(Text, nullable=False, default="", server_default="")
    object_process = Column(Text, nullable=False, default="", server_default="")
    coupling = Column(Text, nullable=False, default="", server_default="")
    empty_ok = Column(Text, nullable=False, default="", server_default="")
    inject_keys = Column(JSONB, nullable=False, default=list)


# 5. 抽象设备模板表
class AbstractDeviceTemplate(Base):
    __tablename__ = "abstract_device_templates"
    a_name = Column(String(50), primary_key=True)
    effect_set = Column(JSONB, nullable=False)
    template_set = Column(JSONB, nullable=False)
    # 跨生态类型码（miot:air-conditioner / google:ac_unit / ohos:smarthumidifier）
    type_keys = Column(JSONB, nullable=False, default=list)
    # 商品名/文件名别名（不含泛词如「灯」「机」）；a_name 本身在匹配时自动计入
    aliases = Column(JSONB, nullable=False, default=list)
    guidance_family = Column(
        String(32),
        ForeignKey("device_guidance_packs.pack_id"),
        nullable=True,
        index=True,
    )

# 5. 具体设备实例表
# source: 1=miot, 2=google home, 3=openharmony
DEVICE_SOURCE_MIOT = 1
DEVICE_SOURCE_GOOGLE_HOME = 2
DEVICE_SOURCE_OPENHARMONY = 3
DEVICE_SOURCE_LABELS = {
    DEVICE_SOURCE_MIOT: "miot",
    DEVICE_SOURCE_GOOGLE_HOME: "google home",
    DEVICE_SOURCE_OPENHARMONY: "openharmony",
}


class ConcreteDevice(Base):
    __tablename__ = "concrete_devices"
    __table_args__ = (
        CheckConstraint("source IN (1, 2, 3)", name="ck_concrete_devices_source"),
    )

    c_instance_id = Column(String(100), primary_key=True)
    c_brand = Column(String(50), nullable=False)
    a_ref = Column(String(50), ForeignKey("abstract_device_templates.a_name"), nullable=True)
    # 设置 index=True 以支持 GIN 索引，优化环境属性的交并集查询
    env_set = Column(JSONB, index=True)
    # 智能家居生态来源：1=miot，2=google home，3=openharmony
    source = Column(Integer, nullable=False, default=DEVICE_SOURCE_MIOT, server_default="1", index=True)
    # 设备能力摘要（抽取生成，供意图 L4 检索；与用户 preference_desc 分离）
    c_desc = Column(Text, nullable=True) 

# 6. 功能指令载荷表
CAPABILITY_KIND_EFFECT = "effect"
CAPABILITY_KIND_AUXILIARY = "auxiliary"
CAPABILITY_KIND_PARAMETER = "parameter"
CAPABILITY_KIND_STRATEGY = "strategy"
CAPABILITY_KINDS = {
    CAPABILITY_KIND_EFFECT,
    CAPABILITY_KIND_AUXILIARY,
    CAPABILITY_KIND_PARAMETER,
    CAPABILITY_KIND_STRATEGY,
}
CAPABILITY_KIND_LABELS = {
    CAPABILITY_KIND_EFFECT: "效果能力",
    CAPABILITY_KIND_AUXILIARY: "辅助能力",
    CAPABILITY_KIND_PARAMETER: "参数能力",
    CAPABILITY_KIND_STRATEGY: "场景策略",
}


def normalize_capability_kind(kind, e_id=None) -> str:
    k = str(kind or "").strip()
    if k in CAPABILITY_KINDS:
        return k
    return CAPABILITY_KIND_AUXILIARY if e_id is None else CAPABILITY_KIND_EFFECT


def kind_keeps_supports(kind) -> bool:
    return str(kind or "").strip() in {CAPABILITY_KIND_PARAMETER, CAPABILITY_KIND_STRATEGY}


def normalize_supports_e_ids(raw) -> list:
    if not raw or not isinstance(raw, list):
        return []
    out = []
    seen = set()
    for x in raw:
        try:
            value = int(x)
        except (TypeError, ValueError):
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


class CommandPayload(Base):
    __tablename__ = "command_payloads"
    __table_args__ = (
        CheckConstraint(
            "capability_kind IN ('effect', 'auxiliary', 'parameter', 'strategy')",
            name="ck_command_payloads_capability_kind",
        ),
    )

    uid = Column(String(256), primary_key=True)
    c_instance_id = Column(String(100), ForeignKey("concrete_devices.c_instance_id"))
    e_id = Column(Integer, ForeignKey("sys_effects.e_id"), nullable=True)
    api_set = Column(JSONB, nullable=False)
    env_impact = Column(JSONB, nullable=True)
    param_schema = Column(JSONB, nullable=True)
    capability_kind = Column(
        String(20),
        nullable=False,
        default=CAPABILITY_KIND_EFFECT,
        server_default=CAPABILITY_KIND_EFFECT,
        index=True,
    )
    capability_desc = Column(Text, nullable=True)
    interpretation = Column(JSONB, nullable=True)
    aligned_template_id = Column(String(200), nullable=True)
    # 参数/场景策略弱引用的效果节点（不写入 e_id，不作为意图实现）
    supports_e_ids = Column(JSONB, nullable=False, default=list)


# 6b. 能力配方（原子指令有序组合，供后续意图展开；本期只落盘/入库）
class CommandRecipe(Base):
    __tablename__ = "command_recipes"

    recipe_uid = Column(String(256), primary_key=True)
    c_instance_id = Column(
        String(100),
        ForeignKey("concrete_devices.c_instance_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipe_name = Column(String(200), nullable=False)
    covers_effects = Column(JSONB, nullable=True)
    needs_auxiliary = Column(JSONB, nullable=True)
    steps = Column(JSONB, nullable=False)
    extra = Column(JSONB, nullable=True)

# 7. 环境属性表（抽取匹配用的小本体：名称 + 解释 + 别名/单位/关联节点）
ENV_KIND_AMBIENT = "ambient"
ENV_KIND_WORKPIECE_ID = "workpiece_id"
ENV_KIND_WORKPIECE_STATE = "workpiece_state"
ENV_KIND_PROVISION = "provision"
ENV_KIND_PROCESS = "process"
ENV_KINDS = {
    ENV_KIND_AMBIENT,
    ENV_KIND_WORKPIECE_ID,
    ENV_KIND_WORKPIECE_STATE,
    ENV_KIND_PROVISION,
    ENV_KIND_PROCESS,
}
ENV_KIND_LABELS = {
    ENV_KIND_AMBIENT: "处境量",
    ENV_KIND_WORKPIECE_ID: "对象身份",
    ENV_KIND_WORKPIECE_STATE: "对象状态量",
    ENV_KIND_PROVISION: "供给能力",
    ENV_KIND_PROCESS: "过程状态",
}


def normalize_env_kind(kind) -> str:
    k = str(kind or "").strip()
    if k in ENV_KINDS:
        return k
    return ENV_KIND_AMBIENT


class SysEnvAttribute(Base):
    __tablename__ = "sys_env_attributes"
    __table_args__ = (
        CheckConstraint(
            "env_kind IN ('ambient', 'workpiece_id', 'workpiece_state', 'provision', 'process')",
            name="ck_sys_env_attributes_env_kind",
        ),
    )

    env_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    env_name = Column(String(50), unique=True, index=True, nullable=False)
    env_desc = Column(Text, nullable=True)
    match_key = Column(String(50), nullable=True, index=True)
    env_kind = Column(
        String(32),
        nullable=False,
        default=ENV_KIND_AMBIENT,
        server_default=ENV_KIND_AMBIENT,
        index=True,
    )
    aliases = Column(JSONB, nullable=False, default=list)
    units = Column(JSONB, nullable=False, default=list)
    related_o_ids = Column(JSONB, nullable=False, default=list)
    related_e_ids = Column(JSONB, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")


# 8. 用户设备偏好（意图检索参与池，与客观知识分离）
class UserDevicePreference(Base):
    __tablename__ = "user_device_preferences"
    __table_args__ = (
        CheckConstraint("weight >= 0 AND weight <= 5", name="ck_udp_weight"),
    )

    c_instance_id = Column(
        String(100),
        ForeignKey("concrete_devices.c_instance_id", ondelete="CASCADE"),
        primary_key=True,
    )
    weight = Column(Integer, nullable=False, default=0, index=True)
    preference_desc = Column(Text, nullable=True)


# 9. 用户指令偏好（原子指令细粒度）
class UserCommandPreference(Base):
    __tablename__ = "user_command_preferences"
    __table_args__ = (
        CheckConstraint("weight >= 0 AND weight <= 5", name="ck_ucp_weight"),
    )

    payload_uid = Column(
        String(256),
        ForeignKey("command_payloads.uid", ondelete="CASCADE"),
        primary_key=True,
    )
    weight = Column(Integer, nullable=False, default=0, index=True)
    preference_desc = Column(Text, nullable=True)
    param_details = Column(JSONB, nullable=True)


# 10. 环境表单（意图实现前的家居库）
PRESET_ROOM_TYPE_NAMES = (
    "客厅",
    "餐厅",
    "卧室",
    "洗手间",
    "厨房",
    "书房",
    "阳台",
    "走廊",
)


class HomeForm(Base):
    __tablename__ = "home_forms"

    form_id = Column(String(64), primary_key=True)
    name = Column(String(100), nullable=False)
    note = Column(Text, nullable=True)


class HomeRoomType(Base):
    __tablename__ = "home_room_types"

    type_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    is_preset = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")


class HomeRoom(Base):
    __tablename__ = "home_rooms"

    room_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    form_id = Column(
        String(64),
        ForeignKey("home_forms.form_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type_id = Column(
        Integer,
        ForeignKey("home_room_types.type_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    label = Column(String(50), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")


class HomeDevicePlacement(Base):
    __tablename__ = "home_device_placements"
    __table_args__ = (
        CheckConstraint("weight >= 1 AND weight <= 5", name="ck_hdp_weight"),
    )

    placement_id = Column(String(64), primary_key=True)
    form_id = Column(
        String(64),
        ForeignKey("home_forms.form_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    catalog_c_instance_id = Column(
        String(100),
        ForeignKey("concrete_devices.c_instance_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    room_id = Column(
        Integer,
        ForeignKey("home_rooms.room_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    alias = Column(String(100), nullable=False, default="")
    weight = Column(Integer, nullable=False, default=1, server_default="1")
    preference_desc = Column(Text, nullable=True)


class HomeCommandPref(Base):
    __tablename__ = "home_command_prefs"
    __table_args__ = (
        CheckConstraint("weight >= 0 AND weight <= 5", name="ck_hcp_weight"),
    )

    placement_id = Column(
        String(64),
        ForeignKey("home_device_placements.placement_id", ondelete="CASCADE"),
        primary_key=True,
    )
    payload_uid = Column(
        String(256),
        ForeignKey("command_payloads.uid", ondelete="CASCADE"),
        primary_key=True,
    )
    weight = Column(Integer, nullable=False, default=1, server_default="1")
    preference_desc = Column(Text, nullable=True)
    param_details = Column(JSONB, nullable=True)