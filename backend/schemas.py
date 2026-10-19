from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class EnvComboItem(BaseModel):
    env_id: Optional[int] = None
    env_name: str
    match_key: str
    role: str = Field(description="primary / side / observe / forbid")
    polarity: str = ""


class EnvComboView(BaseModel):
    empty: bool = False
    note: str = ""
    items: List[EnvComboItem] = Field(default_factory=list)


class EnvRelatedNode(BaseModel):
    id: int
    name: str
    role: Optional[str] = None


# ==========================================
# 一级领域 (Domain)
# ==========================================

# 用户向系统提交“新增领域”时，需要遵循的格式
class DomainCreate(BaseModel):
    d_name: str
    d_desc: Optional[str] = None

class DomainUpdate(BaseModel):
    d_name: str
    d_desc: Optional[str] = None

# 系统向前端返回“领域信息”时，遵循的格式（比新增多了一个 d_id）
class DomainResponse(BaseModel):
    d_id: int
    d_name: str
    d_desc: Optional[str] = None
    env_combo: EnvComboView = Field(default_factory=EnvComboView)

    class Config:
        from_attributes = True  # 允许直接从 SQLAlchemy 模型读取数据

# ==========================================
# 二级对象 (Object)
# ==========================================
class ObjectCreate(BaseModel):
    d_id: int  # 必须告诉系统，这个对象属于哪一个“一级领域”
    o_name: str
    o_desc: Optional[str] = None

class ObjectUpdate(BaseModel):
    o_name: str
    o_desc: Optional[str] = None

class ObjectResponse(BaseModel):
    o_id: int
    d_id: int
    o_name: str
    o_desc: Optional[str] = None
    env_combo: EnvComboView = Field(default_factory=EnvComboView)

    class Config:
        from_attributes = True

# ==========================================
# 三级效果 (Effect)
# ==========================================
class EffectCreate(BaseModel):
    o_id: int  # 必须告诉系统，这个效果属于哪一个“二级对象”
    e_name: str
    e_desc: Optional[str] = None

class EffectUpdate(BaseModel):
    e_name: str
    e_desc: Optional[str] = None

class EffectResponse(BaseModel):
    e_id: int
    o_id: int
    e_name: str
    e_desc: Optional[str] = None
    env_combo: EnvComboView = Field(default_factory=EnvComboView)

    class Config:
        from_attributes = True

# ==========================================
# 抽象设备模板 (Abstract Device)
# ==========================================
from typing import List, Any

class AbstractDeviceCreate(BaseModel):
    a_name: str  # 设备类型名称，如“空调”
    effect_set: List[int]  # 该设备支持的三级效果 ID 列表 
    template_set: List[str]  # 该设备的能力槽位集合，如 ["开启/关闭空调", "制冷模式"]
    type_keys: List[str] = Field(default_factory=list, description="类型码，如 miot:air-conditioner")
    aliases: List[str] = Field(default_factory=list, description="商品名别名，不含泛词")
    guidance_family: Optional[str] = Field(default=None, description="环境参考族 pack_id，如 climate")

class AbstractDeviceUpdate(BaseModel):
    a_name: str
    effect_set: List[int]
    template_set: List[str]
    type_keys: Optional[List[str]] = None
    aliases: Optional[List[str]] = None
    guidance_family: Optional[str] = None

class AbstractDeviceResponse(BaseModel):
    a_name: str
    effect_set: List[int]
    template_set: List[str]
    type_keys: List[str] = Field(default_factory=list)
    aliases: List[str] = Field(default_factory=list)
    guidance_family: Optional[str] = None
    guidance_family_name: Optional[str] = None

    class Config:
        from_attributes = True


class GuidancePackUpdate(BaseModel):
    display_name: str
    body_text: str = ""
    intent: str = ""
    function_map: str = ""
    forbid: str = ""
    object_process: str = ""
    coupling: str = ""
    empty_ok: str = ""
    inject_keys: List[str] = Field(default_factory=list)


class GuidancePackResponse(BaseModel):
    pack_id: str
    pack_kind: str
    display_name: str
    sort_order: int = 0
    body_text: str = ""
    intent: str = ""
    function_map: str = ""
    forbid: str = ""
    object_process: str = ""
    coupling: str = ""
    empty_ok: str = ""
    inject_keys: List[str] = Field(default_factory=list)
    members: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True

# ==========================================
# 功能模板总结结构
# ==========================================
class DeviceTemplateResult(BaseModel):
    templates: List[str] = Field(description="总结出的功能模板字符串列表")


# ==========================================
# 环境属性 (Environmental Attributes)
# ==========================================
class EnvAttributeCreate(BaseModel):
    env_name: str = Field(description="环境属性名称，例如：温度、湿度、光照度")
    env_desc: Optional[str] = Field(default=None, description="解释：何时标记、何时不要标记")
    match_key: Optional[str] = Field(default=None, description="规则匹配键，如 temperature / humidity")
    env_kind: str = Field(
        default="ambient",
        description="构型：ambient / workpiece_id / workpiece_state / provision / process",
    )
    aliases: List[str] = Field(default_factory=list, description="文档别名，如 室温、设定温度、celsius")
    units: List[str] = Field(default_factory=list, description="常见单位，如 celsius、percentage")
    related_o_ids: List[int] = Field(default_factory=list, description="旁证用的二级对象 ID")
    related_e_ids: List[int] = Field(default_factory=list, description="旁证用的三级效果 ID")
    is_active: bool = Field(default=True, description="停用后不再参与后续抽取匹配")

class EnvAttributeUpdate(BaseModel):
    env_name: str = Field(description="环境属性名称")
    env_desc: Optional[str] = Field(default=None, description="解释：何时标记、何时不要标记")
    match_key: Optional[str] = Field(default=None, description="规则匹配键，如 temperature / humidity")
    env_kind: Optional[str] = Field(
        default=None,
        description="构型：ambient / workpiece_id / workpiece_state / provision / process；省略则保持原值",
    )
    aliases: List[str] = Field(default_factory=list, description="文档别名")
    units: List[str] = Field(default_factory=list, description="常见单位")
    related_o_ids: List[int] = Field(default_factory=list, description="旁证用的二级对象 ID")
    related_e_ids: List[int] = Field(default_factory=list, description="旁证用的三级效果 ID")
    is_active: bool = Field(default=True, description="是否启用")

class EnvAttributeResponse(BaseModel):
    env_id: int
    env_name: str
    env_desc: Optional[str] = None
    match_key: Optional[str] = None
    env_kind: str = "ambient"
    aliases: List[str] = Field(default_factory=list)
    units: List[str] = Field(default_factory=list)
    related_o_ids: List[int] = Field(default_factory=list)
    related_e_ids: List[int] = Field(default_factory=list)
    related_objects: List[EnvRelatedNode] = Field(default_factory=list)
    related_effects: List[EnvRelatedNode] = Field(default_factory=list)
    is_active: bool = True

    class Config:
        from_attributes = True


# ==========================================
# 具体设备 (Concrete Device)
# ==========================================
# source: 1=miot, 2=google home, 3=openharmony
DEVICE_SOURCE_MIOT = 1
DEVICE_SOURCE_GOOGLE_HOME = 2
DEVICE_SOURCE_OPENHARMONY = 3


class ConcreteDeviceCreate(BaseModel):
    c_instance_id: str = Field(description="具体设备id，如：urn:miot-spec-v2:device:air-conditioner:0000A004:xiaomi-mc2:1")
    c_brand: Optional[str] = Field(default=None, description="具体设备名称，如：小米互联网空调A（1.5匹_变频_一级能效）")
    a_ref: Optional[str] = Field(default=None, description="所属的抽象设备类型，如：空调；未定类可为空")
    env_set: List[int] = Field(default_factory=list, description="影响或感知的环境属性ID列表")
    source: int = Field(
        default=DEVICE_SOURCE_MIOT,
        description="智能家居生态来源：1=miot，2=google home，3=openharmony",
        ge=1,
        le=3,
    )
    c_desc: Optional[str] = Field(default=None, description="设备能力摘要，供意图检索")

class ConcreteDeviceUpdate(BaseModel):
    c_brand: Optional[str] = Field(default=None, description="具体设备名称")
    a_ref: Optional[str] = Field(default=None, description="所属的抽象设备类型；空字符串表示待确认")
    env_set: List[int] = Field(default_factory=list, description="环境属性ID列表")
    source: Optional[int] = Field(
        default=None,
        description="智能家居生态来源：1=miot，2=google home，3=openharmony",
        ge=1,
        le=3,
    )
    c_desc: Optional[str] = Field(default=None, description="设备能力摘要")

class ConcreteDeviceResponse(BaseModel):
    c_instance_id: str
    c_brand: str
    a_ref: Optional[str] = None
    env_set: List[int]
    source: int = Field(description="智能家居生态来源：1=miot，2=google home，3=openharmony")
    source_label: str = Field(
        default="", description="来源可读标签：miot / google home / openharmony"
    )
    c_desc: Optional[str] = None

    class Config:
        from_attributes = True


class ConcreteDeviceBulkDelete(BaseModel):
    c_instance_ids: List[str] = Field(min_length=1, description="待删除的具体设备实例 ID 列表")


class ConcreteDeviceBulkDeleteResult(BaseModel):
    message: str
    deleted_count: int = 0
    skipped: List[str] = Field(default_factory=list)
    details: List[Dict[str, Any]] = Field(default_factory=list)


# ==========================================
# 功能指令载荷 (Command Payload)
# ==========================================
class CommandPayloadCreate(BaseModel):
    uid: str = Field(description="唯一指令标识")
    c_instance_id: str = Field(description="具体设备 URN")
    e_id: Optional[int] = Field(default=None, description="关联的三级效果 ID；辅助能力可为空")
    api_set: Any = Field(description="具体的 API 调用参数载荷（JSON，可为 list 或 dict）")
    env_impact: List[int] = Field(default_factory=list, description="影响的环境属性 ID 列表")
    param_schema: Optional[Any] = Field(default=None, description="参数占位语义（从设备文档提取）")
    capability_kind: str = Field(
        default="effect",
        description="effect=效果能力，auxiliary=辅助能力，parameter=参数能力，strategy=场景策略",
    )
    capability_desc: Optional[str] = Field(default=None, description="功能解读文本")
    interpretation: Optional[Any] = Field(default=None, description="结构化解读")
    aligned_template_id: Optional[str] = Field(default=None, description="对齐到的抽象模板句")
    supports_e_ids: List[int] = Field(
        default_factory=list,
        description="参数/场景策略弱引用的效果 ID；效果/辅助能力为空列表",
    )

class CommandPayloadUpdate(BaseModel):
    c_instance_id: str = Field(description="具体设备 URN")
    e_id: Optional[int] = Field(default=None, description="关联的三级效果 ID")
    api_set: Any = Field(description="具体的 API 调用参数载荷")
    env_impact: List[int] = Field(default_factory=list, description="影响的环境属性 ID 列表")
    param_schema: Optional[Any] = Field(default=None, description="参数占位语义")
    capability_kind: Optional[str] = Field(default=None)
    capability_desc: Optional[str] = Field(default=None)
    interpretation: Optional[Any] = Field(default=None)
    aligned_template_id: Optional[str] = Field(default=None)
    supports_e_ids: Optional[List[int]] = Field(default=None)

class CommandPayloadResponse(BaseModel):
    uid: str
    c_instance_id: str
    e_id: Optional[int] = Field(
        default=None,
        description="关联的三级效果 ID；辅助能力为空",
    )
    api_set: Any
    env_impact: List[int]
    param_schema: Optional[Any] = None
    capability_kind: str = "effect"
    capability_desc: Optional[str] = None
    interpretation: Optional[Any] = None
    aligned_template_id: Optional[str] = None
    supports_e_ids: List[int] = Field(default_factory=list)

    class Config:
        from_attributes = True


class CommandPayloadTreeKey(BaseModel):
    """分类树等场景仅需设备与效果关联，不含 api_set，避免全量载荷过大。"""

    uid: str
    c_instance_id: str
    e_id: int
    env_impact: List[int] = Field(default_factory=list)


class CommandPayloadBrief(BaseModel):
    """设备详情页用的轻量词条，不含 api_set。"""

    uid: str
    c_instance_id: str
    e_id: Optional[int] = None
    env_impact: List[int] = Field(default_factory=list)
    has_param_slots: bool = False
    capability_kind: str = "effect"
    capability_desc: Optional[str] = None
    supports_e_ids: List[int] = Field(default_factory=list)
    l5_visible: bool = True
    exposure: Optional[str] = None
    specializes_uid: Optional[str] = None
    strategy_subtype: Optional[str] = None


class CommandRecipeResponse(BaseModel):
    recipe_uid: str
    c_instance_id: str
    recipe_name: str
    covers_effects: List[int] = Field(default_factory=list)
    needs_auxiliary: List[str] = Field(default_factory=list)
    steps: List[Any] = Field(default_factory=list)
    extra: Optional[Any] = None

    class Config:
        from_attributes = True


# ==========================================
# 用户设备 / 指令偏好
# ==========================================
class UserDevicePreferenceUpsert(BaseModel):
    weight: int = Field(ge=0, le=5, description="0=不参与检索，1~5 越高越优先")
    preference_desc: Optional[str] = Field(default=None, description="自然语言偏好描述")


class UserDevicePreferenceResponse(BaseModel):
    c_instance_id: str
    weight: int
    preference_desc: Optional[str] = None
    c_brand: Optional[str] = None
    a_ref: Optional[str] = None

    class Config:
        from_attributes = True


class UserDevicePreferenceBatchInit(BaseModel):
    weight: int = Field(default=1, ge=0, le=5, description="批量初始化权重")
    preference_desc: Optional[str] = None
    only_missing: bool = Field(default=True, description="仅补齐尚无偏好行的设备")


class UserCommandPreferenceUpsert(BaseModel):
    weight: int = Field(ge=0, le=5)
    preference_desc: Optional[str] = None
    param_details: Optional[Any] = Field(default=None, description="参数级偏好/默认项")


class UserCommandPreferenceResponse(BaseModel):
    payload_uid: str
    weight: int
    preference_desc: Optional[str] = None
    param_details: Optional[Any] = None
    c_instance_id: Optional[str] = None
    e_id: Optional[int] = None

    class Config:
        from_attributes = True


class UserCommandPreferenceBatchInit(BaseModel):
    weight: int = Field(default=1, ge=0, le=5)
    preference_desc: Optional[str] = None
    only_missing: bool = Field(default=True)


class UserPreferenceBulkApply(BaseModel):
    """对勾选的具体设备批量设置设备权重，和/或其下全部指令权重。"""

    c_instance_ids: List[str] = Field(min_length=1, description="勾选的具体设备实例 ID 列表")
    device_weight: Optional[int] = Field(
        default=None, ge=0, le=5, description="若指定则批量 upsert 设备偏好权重"
    )
    command_weight: Optional[int] = Field(
        default=None, ge=0, le=5, description="若指定则批量 upsert 这些设备下全部指令偏好权重"
    )


class UserPreferenceBulkApplyResult(BaseModel):
    device_upserted: int = 0
    command_upserted: int = 0
    skipped_missing_devices: List[str] = Field(default_factory=list)
    message: str = ""


# ==========================================
# 环境表单 / 家居库
# ==========================================
class HomeFormCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    note: Optional[str] = None


class HomeFormUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    note: Optional[str] = None


class HomeFormResponse(BaseModel):
    form_id: str
    name: str
    note: str = ""


class HomeRoomTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)


class HomeRoomTypeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    is_active: Optional[bool] = None


class HomeRoomTypeResponse(BaseModel):
    type_id: int
    name: str
    is_preset: bool = False
    is_active: bool = True


class HomeRoomCreate(BaseModel):
    type_id: int
    label: Optional[str] = Field(default=None, max_length=50)


class HomeRoomUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=50)
    sort_order: Optional[int] = None


class HomeRoomResponse(BaseModel):
    room_id: int
    form_id: str
    type_id: int
    type_name: str = ""
    label: str
    sort_order: int = 0


class HomePlacementCreate(BaseModel):
    catalog_c_instance_id: str
    alias: Optional[str] = Field(default=None, max_length=100)
    room_id: Optional[int] = None
    weight: int = Field(default=1, ge=1, le=5)
    preference_desc: Optional[str] = None


class HomePlacementUpdate(BaseModel):
    alias: Optional[str] = Field(default=None, max_length=100)
    room_id: Optional[int] = None
    clear_room: bool = False
    weight: Optional[int] = Field(default=None, ge=1, le=5)
    preference_desc: Optional[str] = None


class HomePlacementResponse(BaseModel):
    placement_id: str
    form_id: str
    catalog_c_instance_id: str
    c_brand: str = ""
    a_ref: Optional[str] = None
    env_set: List[int] = Field(default_factory=list)
    source: int = 1
    c_desc: Optional[str] = None
    room_id: Optional[int] = None
    room_label: str = ""
    room_type_name: str = ""
    alias: str = ""
    weight: int = 1
    preference_desc: Optional[str] = None
    display_name: str = ""


class HomeCommandPrefUpsert(BaseModel):
    weight: int = Field(ge=0, le=5)
    preference_desc: Optional[str] = None
    param_details: Optional[Any] = None


class HomeCommandPrefResponse(BaseModel):
    placement_id: str
    payload_uid: str
    weight: int
    preference_desc: Optional[str] = None
    param_details: Optional[Any] = None
    e_id: Optional[int] = None
    e_name: str = ""
    capability_kind: Optional[str] = None
    kind_label: str = ""
    capability_desc: Optional[str] = None
    env_impact: List[int] = Field(default_factory=list)
    env_names: List[str] = Field(default_factory=list)
    supports_e_ids: List[int] = Field(default_factory=list)
    supports_effect_names: List[str] = Field(default_factory=list)
    covered_by_recipes: List[str] = Field(default_factory=list)
    l5_visible: bool = True
    exposure: Optional[str] = None
    specializes_uid: Optional[str] = None
    param_labels: List[str] = Field(default_factory=list)


class HomeRecipeStepCard(BaseModel):
    uid: str
    role: str = ""
    role_label: str = ""
    capability_kind: str = ""
    kind_label: str = ""
    capability_desc: Optional[str] = None
    e_id: Optional[int] = None
    e_name: str = ""
    weight_editable: bool = False
    weight: Optional[int] = None
    shared_recipe_names: List[str] = Field(default_factory=list)
    param_labels: List[str] = Field(default_factory=list)


class HomeRecipeWeightCard(BaseModel):
    recipe_uid: str
    recipe_name: str
    recipe_desc: Optional[str] = None
    daily_use: Optional[str] = None
    pattern: Optional[str] = None
    is_strategy: bool = False
    is_lazy: bool = False
    shadowed: bool = False
    shadowed_by: List[str] = Field(default_factory=list)
    covers_effects: List[int] = Field(default_factory=list)
    cover_effect_names: List[str] = Field(default_factory=list)
    steps: List[HomeRecipeStepCard] = Field(default_factory=list)
    effective_weight: int = 0
    weight_payload_uids: List[str] = Field(default_factory=list)


class HomeCommandEditorResponse(BaseModel):
    placement_id: str
    commands: List[HomeCommandPrefResponse] = Field(default_factory=list)
    recipes: List[HomeRecipeWeightCard] = Field(default_factory=list)
    uncovered_payload_uids: List[str] = Field(default_factory=list)


class HomeCommandPrefBatchItem(BaseModel):
    payload_uid: str
    weight: int = Field(ge=0, le=5)
    preference_desc: Optional[str] = None
    param_details: Optional[Any] = None


class HomeCommandPrefBatchUpsert(BaseModel):
    items: List[HomeCommandPrefBatchItem] = Field(min_length=1)


class HomePlacementBatchCreate(BaseModel):
    catalog_c_instance_ids: List[str] = Field(min_length=1)
    room_id: Optional[int] = None
    weight: int = Field(default=1, ge=1, le=5)
    preference_desc: Optional[str] = None


class HomePlacementBatchPatch(BaseModel):
    placement_ids: List[str] = Field(min_length=1)
    weight: Optional[int] = Field(default=None, ge=1, le=5)
    command_weight: Optional[int] = Field(default=None, ge=0, le=5)


class HomeFormBundleResponse(BaseModel):
    form: HomeFormResponse
    rooms: List[HomeRoomResponse] = Field(default_factory=list)
    placements: List[HomePlacementResponse] = Field(default_factory=list)
    command_prefs: List[HomeCommandPrefResponse] = Field(default_factory=list)


# ==========================================
# 意图实现
# ==========================================
class IntentResolveOptions(BaseModel):
    filter_objects_by_l1: bool = True
    filter_effects_by_l2: bool = True
    filter_commands_by_l3: bool = True
    timeout_per_layer_ms: int = Field(default=180000, ge=5000, le=600000)
    resolve_mode: str = Field(
        default="auto",
        description="auto=自动意图选择（托管）；interactive=复杂意图选择（逐步卡片并列备选）",
    )
    max_options_per_step: int = Field(default=5, ge=2, le=10, description="复杂模式下每步最多展示备选数")
    allowed_sources: List[int] = Field(
        default_factory=lambda: [1, 2, 3],
        description="参与本次实现的生态来源：1=miot，2=google home，3=openharmony；默认全选",
    )
    home_form_id: Optional[str] = Field(
        default=None,
        description="当前环境表单 ID；意图实现只在该表单已实例化的设备上收敛",
    )


class IntentResolveRequest(BaseModel):
    intent_text: str = Field(min_length=1, description="自然语言意图")
    options: IntentResolveOptions = Field(default_factory=IntentResolveOptions)


class IntentSelectedNode(BaseModel):
    id: Any
    name: str = ""
    reason: str = ""
    env_hint: str = ""
    env_match_score: int = 0
    candidate_kind: str = ""


class IntentRelation(BaseModel):
    type: str = Field(description="cooperate | mutex | sequence | alternative")
    from_id: Any
    to_id: Any
    note: str = ""


class IntentLayerResult(BaseModel):
    layer: str
    selected_nodes: List[IntentSelectedNode] = Field(default_factory=list)
    relations: List[IntentRelation] = Field(default_factory=list)
    nl_guidance: str = ""
    invalid_ids: List[Any] = Field(default_factory=list)
    candidate_count: int = 0
    stopped: bool = False
    stop_reason: Optional[str] = None
    error: Optional[str] = None
    wanted_env: List[str] = Field(default_factory=list)


class IntentPlanParamPlaceholder(BaseModel):
    path: str
    hint: str = ""
    nl_description: Optional[str] = None
    user_value: Optional[Any] = None
    label: Optional[str] = None
    value_type: Optional[str] = None
    options: Optional[List[Any]] = None
    value_range: Optional[Any] = None
    siid: Optional[Any] = None
    piid: Optional[Any] = None
    unit: Optional[str] = None
    required: bool = True


class IntentCommandVariant(BaseModel):
    """同一具体设备下、达成相同意图目标的不同指令路径。"""
    payload_uid: str
    nl_step: str = ""
    is_recommended: bool = False
    variant_reason: str = ""
    goal_analysis: str = ""
    command_weight: int = 0
    api_set: Any = None
    param_placeholders: List[IntentPlanParamPlaceholder] = Field(default_factory=list)


class IntentStepOption(BaseModel):
    payload_uid: str
    c_instance_id: str = ""
    c_brand: str = ""
    e_id: Optional[int] = None
    e_name: str = ""
    nl_step: str = ""
    is_recommended: bool = False
    tie_group: str = ""
    tie_reason: str = ""
    device_weight: int = 0
    command_weight: int = 0
    goal_analysis: str = ""
    api_set: Any = None
    param_placeholders: List[IntentPlanParamPlaceholder] = Field(default_factory=list)
    command_variants: List[IntentCommandVariant] = Field(
        default_factory=list,
        description="同设备同目标的指令路径备选；仅在严格满足意图时非空",
    )


class IntentPlanStep(BaseModel):
    step: int
    payload_uid: str
    selected_uid: str = ""
    step_intent: str = ""
    c_instance_id: str = ""
    c_brand: str = ""
    e_id: Optional[int] = None
    e_name: str = ""
    api_set: Any = None
    param_placeholders: List[IntentPlanParamPlaceholder] = Field(default_factory=list)
    nl_step: str = ""
    options: List[IntentStepOption] = Field(default_factory=list)
    selection_required: bool = False


class IntentFinalPlan(BaseModel):
    plan_summary: str = ""
    ordered_steps: List[IntentPlanStep] = Field(default_factory=list)
    relations: List[IntentRelation] = Field(default_factory=list)
    nl_guidance: str = ""
    resolve_mode: str = "auto"
    weight_rank_decisions: List[Any] = Field(
        default_factory=list,
        description="L5 按设备/指令权重择优的决策摘要",
    )


class IntentResolveResponse(BaseModel):
    trace_id: str
    intent_text: str
    layers: Dict[str, IntentLayerResult]
    final_plan: Optional[IntentFinalPlan] = None
    stopped_at: Optional[str] = None
    message: Optional[str] = None
    trace_log_file: Optional[str] = Field(default=None, description="本次意图寻址日志文件路径")


class IntentPackRequest(BaseModel):
    trace_id: Optional[str] = Field(default=None, description="关联的意图寻址 trace_id")
    intent_text: str = Field(min_length=1, description="用户原意图")
    final_plan: IntentFinalPlan
    user_param_values: Dict[str, Any] = Field(
        default_factory=dict,
        description="用户填写的参数，键为「步骤号-path」，如 1-api_set[0].value",
    )


class IntentPackedStep(BaseModel):
    step: int
    payload_uid: str
    c_instance_id: str = ""
    c_brand: str = ""
    e_id: Optional[int] = None
    e_name: str = ""
    nl_step: str = ""
    step_description: str = ""
    user_params: List[Dict[str, Any]] = Field(default_factory=list)
    api_set: Any = None


class IntentPackResponse(BaseModel):
    success: bool = True
    message: str = ""
    plan_summary: str = ""
    resolve_mode: str = Field(default="auto", description="auto=自动模式，interactive=复杂模式")
    resolve_mode_label: str = Field(default="自动模式", description="调用模式中文名")
    packed_steps: List[IntentPackedStep] = Field(default_factory=list)
    packed_api_set: List[Dict[str, Any]] = Field(default_factory=list)
    log_file: Optional[str] = Field(default=None, description="API 指令集生成日志路径")
    validation_errors: List[str] = Field(default_factory=list)

