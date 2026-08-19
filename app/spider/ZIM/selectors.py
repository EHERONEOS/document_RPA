SYS_EXCEPTION_P = (
    "x://*[contains(concat(' ', normalize-space(@class), ' '), ' container ')]/p[contains(normalize-space(), '该功能正在维护')]",
    "系统维护提示",
)
DC_MENU = ("x://div[@data-action='Place Booking'][contains(string(), '订舱')]", "订舱导航菜单")
DC_LIST_FRAME = ("css:#iframeContainer iframe[src*='/Ebooking/PlaceBooking/List']", "订舱列表框架")
SEARCH_BOOK_NO = ("css:#ref_no", "提单号搜索框")
SEARCH_BTN = ("#btnSearch", "搜索按钮")
BOOKING_GET_LIST_API = "https://cis.zim-logistics.com.cn/Ebooking/PlaceBooking/GetList"
SAVE_SI_API = "https://cis.zim-logistics.com.cn/Ebooking/BookEdit/SaveHblComfirm"


# 表单字段为字典列表，可用键：
#   type            字段类型 (input/select/s_select)
#   locator         元素定位器
#   field           content 字段名
#   name            元素名称
#   skip_if_empty   空值跳过校验
#   option_selector s_select 搜索结果定位器
#   partial_match   部分匹配校验
SI_BASE_FILL_FIELDS = [
    {"type": "input", "locator": "#shp_name", "field": "shipperTitle", "name": "发货人"},
    {"type": "input", "locator": "#shp_address", "field": "shipperAddress", "name": "发货人地址"},
    {"type": "input", "locator": "#Cns_name", "field": "consigneeTitle", "name": "收货人"},
    {"type": "input", "locator": "#cns_address", "field": "consigneeAddress", "name": "收货人地址"},
    {"type": "input", "locator": "#nty_name", "field": "notifyTitle", "name": "通知人"},
    {"type": "input", "locator": "#nty_address", "field": "notifyAddress", "name": "通知人地址"},
    {"type": "input", "locator": "#conf_no", "field": "scNo", "name": "合约号", "skip_if_empty": True},
    {"type": "select", "locator": "#pay_term_frt_hbl", "field": "paymentType", "name": "付款方式"},
    {"type": "input", "locator": "#remark", "field": "remarks", "name": "备注", "skip_if_empty": True},
    {"type": "input", "locator": "#HS_code", "field": "totalHsCode", "name": "HS CODE"},
    {"type": "select", "locator": "#pcs_unit_code", "field": "totalAmountUnit", "name": "包装单位"},
    {"type": "input", "locator": "#goods_mark", "field": "totalMarks", "name": "唛头"},
    {"type": "input", "locator": "#goods_desc", "field": "totalGoodsDesc", "name": "货描"},
    {"type": "select", "locator": "#release_type", "field": "releaseMode", "name": "提单类型"},
    {
        "type": "s_select",
        "locator": "#frt_pay_at_code",
        "field": "partyPaymentPlaceCode",
        "name": "付款地代码",
        "skip_if_empty": True,
        "option_selector": "c:.autocomplete-suggestions>.autocomplete-suggestion",
    },
]


ADD_CON_BTN = ("#btnAddContainer", "添加 SI 箱货按钮")
DELETE_CON_BTN = ("c:#tbContainer>tr .hbl_tbtnDel", "删除 SI 箱货按钮")
CON_BODY_ROW = ("c:#tbContainer>tr", "SI 箱货信息行")
SI_CONTAINER_FILL_FIELDS = [
    {"type": "input", "locator": ".container", "field": "containerNo", "name": "箱号"},
    {"type": "input", "locator": ".seal_no", "field": "sealNo", "name": "封号"},
    {"type": "select", "locator": ".cont_size_name", "field": "containerSize", "name": "尺寸"},
    {"type": "select", "locator": ".cont_type", "field": "splitContainerType", "name": "箱型"},
    {"type": "input", "locator": ".qty", "field": "packages", "name": "件数"},
    {"type": "input", "locator": ".kgs", "field": "grossWeight", "name": "毛重"},
    {"type": "input", "locator": ".cbm", "field": "volume", "name": "体积"},
    {"type": "input", "locator": ".unit", "field": "packageUnit", "name": "包装单位"},
]
SI_SAVE_BTN = ("#Shp_Save", "SI 保存按钮")
SI_SUBMIT_BTN = ("#Shp_Edit", "SI 提交按钮")

SI_VERIFY_FIELDS = [
    *SI_BASE_FILL_FIELDS,
    {"type": "input", "locator": "#frt_pay_at", "field": "partyPaymentPlace", "name": "付款地"},
    {"type": "input", "locator": "#hbl_num", "field": "numberOfOriginal", "name": "提单件数"},
    {"type": "input", "locator": "#pr_name", "field": "receiptPlace", "name": "收货地", "skip_if_empty": True, "partial_match": True},
    {"type": "input", "locator": "#pol_name", "field": "pol", "name": "起运港", "skip_if_empty": True, "partial_match": True},
    {"type": "input", "locator": "#pod_name", "field": "pod", "name": "目的港", "skip_if_empty": True, "partial_match": True},
    {"type": "input", "locator": "#pl_name", "field": "deliveryPlace", "name": "交付地", "skip_if_empty": True, "partial_match": True},
    {"type": "input", "locator": "#fd_name", "field": "finalDestination", "name": "最终目的地", "skip_if_empty": True, "partial_match": True},
    # {"type": "input", "locator": "#cbm_hbl", "field": "totalVolume", "name": "CBM 总体积"},
    # {"type": "input", "locator": "#wgt_hbl", "field": "totalGrossWeight", "name": "KGS 总毛重"},
    # {"type": "input", "locator": "#pcs_hbl", "field": "totalAmount", "name": "Qty 总件数"},
]
ERR_TIP_INFO = ('c:.layui-layer-content', '错误提示信息')



ROW_VGM_A = ("c:.detail>div:nth-child(2) .grid-selected .edit_vgm", "打开 VGM 弹窗按钮")
VGM_ALERT_FRAME = ("c:.layui-layer-content iframe", "VGM 弹窗框架")
VGM_ADD_BTN = ("#btnAddContainer", "添加 VGM 箱货按钮")
VGM_DELETE_BTN = ("c:#tbContainer .hbl_tbtnDel", "删除 VGM 箱货按钮")
VGM_CON_BODY_ROW = ("c:#tbContainer>tr", "VGM 箱货信息行")
VGM_CONTAINER_FILL_FIELDS = [
    {"type": "input", "locator": ".container", "field": "containerNo", "name": "箱号"},
    {"type": "input", "locator": ".seal_no", "field": "sealNo", "name": "封号"},
    {"type": "select", "locator": ".cont_size_name", "field": "containerSize", "name": "尺寸"},
    {"type": "select", "locator": ".cont_type", "field": "splitContainerType", "name": "箱型"},
    {"type": "input", "locator": ".qty", "field": "packages", "name": "件数"},
    {"type": "input", "locator": ".unit", "field": "packageUnit", "name": "包装单位"},
    {"type": "input", "locator": ".kgs", "field": "grossWeight", "name": "毛重"},
    {"type": "input", "locator": ".cbm", "field": "volume", "name": "体积"},
    {"type": "select", "locator": ".vgm_wgt_type", "field": "method", "name": "称重方式"},
    {"type": "input", "locator": ".vgm_wgt", "field": "weight", "name": "重量"},
]
VGM_BASE_FILL_FIELDS = [
    {"type": "input", "locator": "#vgm_man", "field": "contacts", "name": "VGM 联系人"},
    {"type": "input", "locator": "#vgm_tel", "field": "tel", "name": "VGM 联系电话"},
    {"type": "input", "locator": "#vgm_mail", "field": "email", "name": "VGM 邮箱"},
    {"type": "input", "locator": "#vgm_addr", "field": "address", "name": "VGM 地址"},
]
VGM_SUBMIT_BTN = ("x://*[@class='layui-layer-btn0' and normalize-space()='Submit']", "VGM 提交按钮")
