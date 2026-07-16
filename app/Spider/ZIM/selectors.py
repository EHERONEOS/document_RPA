DC_MENU="x://div[@data-action='Place Booking'][contains(string(), '订舱')]" # 订舱导航菜单
DC_LIST_FRAME = "css:#iframeContainer iframe[src*='/Ebooking/PlaceBooking/List']"
SEARCH_BOOK_NO = "css:#ref_no" #提单号
SEARCH_BTN = "#btnSearch" # 搜索按钮
BOOKING_GET_LIST_API = "https://cis.zim-logistics.com.cn/Ebooking/PlaceBooking/GetList" # 订舱列表接口


# 订舱填单字段
SJIPPER="#shp_name"  # 收货人
SJIPPER_ADDRESS="#shp_address" #收货人地址
CONSIGNEE="#Cns_name"  # 收货人
CONSIGNEE_ADDRESS="#cns_address" #收货人地址
NOTIFY = "#nty_name"  # 通知人
NOTIFY_ADDRESS="#nty_address" #通知人人地址

CONTRACT_NO ="#conf_no" #合约号
PAYMENT_TERM = "#pay_term_frt_hbl" #付款方式
REMARK = "#remark" #备注

HS_CODE = "#HS_code" #HS CODE
PCS_UNIT = "#pcs_unit_code" #包装单位
MARK = "#goods_mark" #唛头
DESC = "#goods_desc" #货描
ADD_CON_BTN = "#btnAddContainer" #添加箱货按钮
DELETE_CON_BTN = "c:#tbContainer>tr .hbl_tbtnDel" #删除箱货按钮
CON_BODY_ROW = "c:#tbContainer>tr" #单个箱货行dom 需要后面加上nth-child(1)
CON_ROW_CON_NO =".container"     #箱号 #tbContainer>tr:nth-child(1) .container
CON_ROW_SEAL_NO =".seal_no"      #封号 #tbContainer>tr:nth-child(1) .seal_no
CON_ROW_SIZE =".cont_size_name"  #尺寸 #tbContainer>tr:nth-child(1) .cont_size_name
CON_ROW_CON_TYPE =".cont_type"   #箱型 #tbContainer>tr:nth-child(1) .cont_type
CON_ROW_QTY =".qty"              #件数 #tbContainer>tr:nth-child(1) .qty
CON_ROW_KGS =".kgs"              #毛重 #tbContainer>tr:nth-child(1) .kgs
CON_ROW_CBM =".cbm"              #体积 #tbContainer>tr:nth-child(1) .cbm
CON_ROW_UNIT =".unit"            #包装单位 #tbContainer>tr:nth-child(1) .unit


RELEASE_TYPE ="#release_type" #提单类型
HBL_NUM ="#hbl_num" #提单件数

# SI 基础信息填写配置：(字段类型, 定位器, content 字段名)
SI_BASE_FILL_FIELDS = (
    ("input", SJIPPER, "shipperTitle"),
    ("input", SJIPPER_ADDRESS, "shipperAddress"),
    ("input", CONSIGNEE, "consigneeTitle"),
    ("input", CONSIGNEE_ADDRESS, "consigneeTitle"),
    ("input", NOTIFY, "notifyTitle"),
    ("input", NOTIFY_ADDRESS, "notifyAddress"),
    ("input", CONTRACT_NO, "scNo"),
    ("select", PAYMENT_TERM, "paymentType"),
    ("input", REMARK, "remarks"),
    ("input", HS_CODE, "totalHsCode"),
    ("select", PCS_UNIT, "totalAmountUnit"),
    ("input", MARK, "totalMarks"),
    ("input", DESC, "totalGoodsDesc"),

    ("select", RELEASE_TYPE, "releaseMode"),
    ("input", HBL_NUM, "numberOfOriginal"),
)

# SI 箱货信息填写配置：(字段类型, 定位器, content 字段名)
SI_CONTAINER_FILL_FIELDS = (
    ("input", CON_ROW_CON_NO, "containerNo"),
    ("input", CON_ROW_SEAL_NO, "sealNo"),
    ("select", CON_ROW_SIZE, "containerSize"),
    ("select", CON_ROW_CON_TYPE, "splitContainerType"),
    ("input", CON_ROW_QTY, "packages"),
    ("input", CON_ROW_KGS, "grossWeight"),
    ("input", CON_ROW_CBM, "volume"),
    ("input", CON_ROW_UNIT, "packageUnit"),
)


# 基于填写配置自动派生校验配置，避免填写和校验维护两套字段映射。
SI_BASE_INPUT_FIELDS = tuple((locator, field_name) for field_type, locator, field_name in SI_BASE_FILL_FIELDS if field_type == "input")
SI_BASE_SELECT_FIELDS = tuple((locator, field_name) for field_type, locator, field_name in SI_BASE_FILL_FIELDS if field_type == "select")
SI_CONTAINER_INPUT_FIELDS = tuple((locator, field_name) for field_type, locator, field_name in SI_CONTAINER_FILL_FIELDS if field_type == "input")
SI_CONTAINER_SELECT_FIELDS = tuple((locator, field_name) for field_type, locator, field_name in SI_CONTAINER_FILL_FIELDS if field_type == "select")



ROW_VGM_A = "c:.detail>div:nth-child(2) .grid-selected .edit_vgm" # 打开VGM弹窗按钮
VGM_ALERT_FRAME= "c:.layui-layer-content iframe"#VGM弹窗iframe定位

