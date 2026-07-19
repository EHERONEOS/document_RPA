DC_MENU="x://div[@data-action='Place Booking'][contains(string(), '订舱')]" # 订舱导航菜单
DC_LIST_FRAME = "css:#iframeContainer iframe[src*='/Ebooking/PlaceBooking/List']"
SEARCH_BOOK_NO = "css:#ref_no" #提单号
SEARCH_BTN = "#btnSearch" # 搜索按钮
BOOKING_GET_LIST_API = "https://cis.zim-logistics.com.cn/Ebooking/PlaceBooking/GetList" # 订舱列表接口


# SI 基础信息填写配置：(字段类型, 定位器, content 字段名,空值跳过校验, s_select:搜索选项定位器)
SI_BASE_FILL_FIELDS = (
    ("input", "#shp_name", "shipperTitle"), # 发货人
    ("input", "#shp_address", "shipperAddress"), # 发货人地址
    ("input", "#Cns_name", "consigneeTitle"), # 收货人
    ("input", "#cns_address", "consigneeAddress"), # 收货人地址
    ("input", "#nty_name", "notifyTitle"), # 通知人
    ("input", "#nty_address", "notifyAddress"), # 通知人地址
    ("input", "#conf_no", "scNo",True), # 合约号
    ("select", "#pay_term_frt_hbl", "paymentType"), # 付款方式
    ("input", "#remark", "remarks",True), # 备注
    ("input", "#HS_code", "totalHsCode"), # HS CODE
    ("select", "#pcs_unit_code", "totalAmountUnit"), # 包装单位
    ("input", "#goods_mark", "totalMarks"), # 唛头
    ("input", "#goods_desc", "totalGoodsDesc"), # 货描
    ("select", "#release_type", "releaseMode"), # 提单类型
    # ("input", "#hbl_num", "numberOfOriginal"), # 提单件数
    ("s_select", "#frt_pay_at_code","partyPaymentPlace",True,"c:.autocomplete-suggestions>.autocomplete-suggestion"), # 付款地code
)


ADD_CON_BTN = "#btnAddContainer" #添加箱货按钮
DELETE_CON_BTN = "c:#tbContainer>tr .hbl_tbtnDel" #删除箱货按钮
CON_BODY_ROW = "c:#tbContainer>tr" #单个箱货行dom 需要后面加上nth-child(1)
# SI 箱货信息填写配置：(字段类型, 定位器, content 字段名)
SI_CONTAINER_FILL_FIELDS = (
    ("input", ".container" , "containerNo"), # 箱号
    ("input", ".seal_no" , "sealNo"), # 封号
    ("select", ".cont_size_name" , "containerSize"), # 尺寸
    ("select", ".cont_type" , "splitContainerType"), # 箱型
    ("input", ".qty" , "packages"), # 件数
    ("input", ".kgs" , "grossWeight"), # 毛重
    ("input", ".cbm" , "volume"), # 体积
    ("input", ".unit" , "packageUnit"), # 包装单位
)

#需要检验的字段(字段类型, 定位器, content 字段名,空值跳过校验)
SI_VERIFY_FIELDS=(
    *SI_BASE_FILL_FIELDS,
    ("input","#vessel","vessel",True), # 船名
    ("input","#voyage","voyage",True), # 航次
    ("input","#pr_code","receiptPlaceCode",True), # 装货地五字码
    ("input","#pr_name","receiptPlace",True), # 装货地

    ("input","#pol_code","polCode",True), # 起运港五字码
    ("input","#pol_name","pol",True), # 起运港

    ("input","#pod_code","podCode",True), # 目的港五字码
    ("input","#pod_name","pod",True), # 目的港

    ("input","#pl_code","deliveryPlaceCode",True), # 交付地五字码
    ("input","#pl_name","deliveryPlace",True), # 交付地

    # ("input","#fd_code","finalDestinationCode"), # 最终目的地五字码
    ("input","#fd_name","finalDestination",True), # 最终目的地(未定义)
)



ROW_VGM_A = "c:.detail>div:nth-child(2) .grid-selected .edit_vgm" # 打开VGM弹窗按钮
VGM_ALERT_FRAME= "c:.layui-layer-content iframe"#VGM弹窗iframe定位
VGM_ADD_BTN ="#btnAddContainer" # 添加箱货按钮
VGM_DELETE_BTN ="c:#tbContainer .hbl_tbtnDel" # 删除箱货按钮
VGM_CON_BODY_ROW = "c:#tbContainer>tr" #单个箱货行dom 需要后面加上nth-child(1)
# VGM 箱货信息填写配置：(字段类型, 定位器, content 字段名)
VGM_CONTAINER_FILL_FIELDS = (
    ("input", ".container" , "containerNo"), # 箱号
    ("input", ".seal_no" , "sealNo"), # 封号
    ("select", ".cont_size_name" , "containerSize"), # 尺寸
    ("select", ".cont_type" , "splitContainerType"), # 箱型
    ("input", ".qty" , "packages"), # 件数
    ("input", ".unit" , "packageUnit"), # 包装单位
    ("input", ".kgs" , "grossWeight"), # 毛重
    ("input", ".cbm" , "volume"), # 体积
    ("select", ".vgm_wgt_type" , "method"), # 称重方式
    ("input", ".vgm_wgt" , "weight"), # 重量
)
VGM_BASE_FILL_FIELDS= (
    ("input", "#vgm_man", "contacts"), # VGM联系人
    ("input", "#vgm_tel", "tel"), # VGM联系电话
    ("input", "#vgm_mail", "email"), # VGM邮箱
    ("input", "#vgm_addr", "address"), # VGM地址
)

