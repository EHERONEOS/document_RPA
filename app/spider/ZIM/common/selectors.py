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


# 表单字段：(字段类型, 定位器, content 字段名, 元素名称, 空值跳过校验, 搜索结果定位器)
SI_BASE_FILL_FIELDS = (
    ("input", "#shp_name", "shipperTitle", "发货人"),
    ("input", "#shp_address", "shipperAddress", "发货人地址"),
    ("input", "#Cns_name", "consigneeTitle", "收货人"),
    ("input", "#cns_address", "consigneeAddress", "收货人地址"),
    ("input", "#nty_name", "notifyTitle", "通知人"),
    ("input", "#nty_address", "notifyAddress", "通知人地址"),
    ("input", "#conf_no", "scNo", "合约号", True),
    ("select", "#pay_term_frt_hbl", "paymentType", "付款方式"),
    ("input", "#remark", "remarks", "备注", True),
    ("input", "#HS_code", "totalHsCode", "HS CODE"),
    ("select", "#pcs_unit_code", "totalAmountUnit", "包装单位"),
    ("input", "#goods_mark", "totalMarks", "唛头"),
    ("input", "#goods_desc", "totalGoodsDesc", "货描"),
    ("select", "#release_type", "releaseMode", "提单类型"),
    (
        "s_select",
        "#frt_pay_at_code",
        "partyPaymentPlaceCode",
        "付款地代码",
        True,
        "c:.autocomplete-suggestions>.autocomplete-suggestion",
    ),
)


ADD_CON_BTN = ("#btnAddContainer", "添加 SI 箱货按钮")
DELETE_CON_BTN = ("c:#tbContainer>tr .hbl_tbtnDel", "删除 SI 箱货按钮")
CON_BODY_ROW = ("c:#tbContainer>tr", "SI 箱货信息行")
SI_CONTAINER_FILL_FIELDS = (
    ("input", ".container", "containerNo", "箱号"),
    ("input", ".seal_no", "sealNo", "封号"),
    ("select", ".cont_size_name", "containerSize", "尺寸"),
    ("select", ".cont_type", "splitContainerType", "箱型"),
    ("input", ".qty", "packages", "件数"),
    ("input", ".kgs", "grossWeight", "毛重"),
    ("input", ".cbm", "volume", "体积"),
    ("input", ".unit", "packageUnit", "包装单位"),
)
SI_SAVE_BTN = ("#Shp_Save", "SI 保存按钮")
SI_SUBMIT_BTN = ("#Shp_Edit", "SI 提交按钮")

SI_VERIFY_FIELDS = (
    *SI_BASE_FILL_FIELDS,
    ("input", "#frt_pay_at", "partyPaymentPlace", "付款地"),
    ("input", "#hbl_num", "numberOfOriginal", "提单件数"),
    ("input", "#pr_name", "receiptPlace", "装货地", True),
    ("input", "#pol_name", "pol", "起运港", True),
    ("input", "#pod_name", "pod", "目的港", True),
    ("input", "#pl_name", "deliveryPlace", "交付地", True),
    ("input", "#fd_name", "finalDestination", "最终目的地", True),
    # ("input", "#cbm_hbl", "totalVolume", "CBM 总体积"),
    # ("input", "#wgt_hbl", "totalGrossWeight", "KGS 总毛重"),
    # ("input", "#pcs_hbl", "totalAmount", "Qty 总件数"),
)
ERR_TIP_INFO = ('c:.layui-layer-content', '错误提示信息')



ROW_VGM_A = ("c:.detail>div:nth-child(2) .grid-selected .edit_vgm", "打开 VGM 弹窗按钮")
VGM_ALERT_FRAME = ("c:.layui-layer-content iframe", "VGM 弹窗框架")
VGM_ADD_BTN = ("#btnAddContainer", "添加 VGM 箱货按钮")
VGM_DELETE_BTN = ("c:#tbContainer .hbl_tbtnDel", "删除 VGM 箱货按钮")
VGM_CON_BODY_ROW = ("c:#tbContainer>tr", "VGM 箱货信息行")
VGM_CONTAINER_FILL_FIELDS = (
    ("input", ".container", "containerNo", "箱号"),
    ("input", ".seal_no", "sealNo", "封号"),
    ("select", ".cont_size_name", "containerSize", "尺寸"),
    ("select", ".cont_type", "splitContainerType", "箱型"),
    ("input", ".qty", "packages", "件数"),
    ("input", ".unit", "packageUnit", "包装单位"),
    ("input", ".kgs", "grossWeight", "毛重"),
    ("input", ".cbm", "volume", "体积"),
    ("select", ".vgm_wgt_type", "method", "称重方式"),
    ("input", ".vgm_wgt", "weight", "重量"),
)
VGM_BASE_FILL_FIELDS = (
    ("input", "#vgm_man", "contacts", "VGM 联系人"),
    ("input", "#vgm_tel", "tel", "VGM 联系电话"),
    ("input", "#vgm_mail", "email", "VGM 邮箱"),
    ("input", "#vgm_addr", "address", "VGM 地址"),
)
VGM_SUBMIT_BTN = ("x://*[@class='layui-layer-btn0' and normalize-space()='Submit']", "VGM 提交按钮")
