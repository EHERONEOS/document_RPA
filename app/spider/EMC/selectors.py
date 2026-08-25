"""EMC SI 页面定位器。

EMC 仍是传统服务端渲染页面，页面中的稳定 id 与旧 Selenium 流程保持一致。
"""

LOGIN_URL = "https://www.evergreen-shipping.cn/tam1/jsp/TAM1_Login.jsp"
SI_URL = (
    "https://www.evergreen-shipping.cn/servlet/TUF1_ControllerServlet.do?"
    "action=allInOne&lang=zh-CN&defaultFunc=BI"
)
PDF_DOWNLOAD_URL = "https://www.evergreen-shipping.cn/servlet/TUF1_ControllerServlet.do"

LOGIN_USER_INFO = "x://*[@id='LogoUserInfo']"
LOGIN_ACCOUNT = "x://*[@id='id']"
LOGIN_CAPTCHA_IMAGE = "x://*[@id='captchaImg']"
LOGIN_SUBMIT = "x://*[@id='captcha_div']//a[1]"
LOGIN_FORM = "x://*[@id='captcha_div']"
OTP_CONTINUE = "x://*[@id='btn_continue']"

SI_MENU = "x://*[text()='订舱/提单']"
SI_MENU_ITEM = "x://a[text()='提单资料指示']"
SI_CONTACT_PAGE = "x://*[text()='联络方式']"
QUICK_SEARCH_INPUT = "x://*[@id='ebi1_quick_search_text']"
QUICK_SEARCH_BUTTON = "x://*[@id='ebi1_quick_search']"
NEVER_SHOW_CHECKBOX = "x://*[@id='blut_never_show']"
NEVER_SHOW_CONFIRM = "x://*[@id='MB_content']/div/p/button"
BLANK_BILL_BUTTON = "x://*[@id='ebi1OpenBlankForm']"
BLANK_BILL_BOOKING_INPUT = "x://*[@id='bkno']"
MODAL_CONFIRM_BUTTON = "x://*[@id='MB_content']//input[@value='确认']"
# 查询结果会随账号的单据数量变化，不能依赖固定表格/行下标。
SEARCH_RESULT_ROWS = "x://*[@id='ebi1_rightContent']//table[contains(@class, 'Design1')]//*[@align='center'][td]"
SEARCH_RESULT_BOOKING_NO = "xpath:./td[1]"
SEARCH_RESULT_STATUS = "xpath:./td[5]/a"
SEARCH_RESULT_SPLIT_BILL = "xpath:./td[9]/span[1]"
SPLIT_BILL_BOOKING_INPUT = "x://*[@id='copyBKNO']"
SPLIT_BILL_SUBMIT = "x://*[@name='Submit']"
NO_SEARCH_RESULT = "x://*[text()='无符合资料']"
DRAFT_RESULT_ROWS = "x://*[@class='Design1']//*[@align='center']"
DRAFT_PDF = "xpath:.//span[@ectype='modalPdf']"
DRAFT_AIO_UNIQID = "x://*[@id='aio_uniqid']"

COMBINE_BOOKING_BUTTON = "x://*[@id='ebi1_combineBooking']"
COMBINE_BOOKING_INPUT = "x://*[@id='freeBKNO']"
COMBINE_ADD_BUTTON = "x://*[@id='combineForm']//*[@value='添加']"
COMBINE_CONFIRM_BUTTON = "x://*[@id='combineForm']//*[@value='确认']"
MODAL_CLOSE = "x://*[@title='Close window']"

SHIPPER_INPUT = "x://*[@id='SHIPPER_TYPE']"
CONSIGNEE_INPUT = "x://*[@id='CONSIGNEE_TYPE']"
NOTIFY_INPUT = "x://*[@id='NOTIFY_PARTY_1_TYPE']"
SECOND_NOTIFY_INPUT = "x://*[@id='NOTIFY_PARTY_2_TYPE']"
LOCATION_FORMAT = "x://*[@id='ebi1_locFormat']/a"
RECEIPT_PLACE_ALIAS = "x://*[@id='aliasName1']"
POL_ALIAS = "x://*[@id='aliasName2']"
POD_ALIAS = "x://*[@id='aliasName3']"
DELIVERY_PLACE_ALIAS = "x://*[@id='aliasName4']"
LOCATION_ALIAS_CONFIRM = "x://*[@id='MB_content']/fieldset/div/input[1]"
TRANS_SHIPMENT_REQUIREMENTS = "x://*[@id='ONWARD_INLAND_ROUTING_TYPE']"

EORI_SECTION = "x://*[@id='EORI_TD']"
US_SECTION = "x://*[@id='USAMS_TD']"
SHIPPER_EORI = "x://*[@id='ebi1_shprEORI']"
CONSIGNEE_EORI = "x://*[@id='ebi1_cneeEORI']"
NOTIFY_EORI = "x://*[@id='ebi1_nPEORI']"
SECOND_NOTIFY_EORI = "x://*[@id='ebi1_nP1EORI']"
US_SHIPPER = "x://*[@id='US_SHIPPER_TYPE']"
US_CONSIGNEE = "x://*[@id='US_CONSIGNEE_TYPE']"
US_NOTIFY = "x://*[@id='US_NOTIFY_PARTY_1_TYPE']"
US_SECOND_NOTIFY = "x://*[@id='US_NOTIFY_PARTY_2_TYPE']"
NVO_SCAC = "x://*[@id='NVO_SCAC']"
US_MORE_NOTIFY_TOGGLE = "x://*[@id='openUSNotifyParty']/a"
US_MORE_NOTIFY = "x://*[@id='US_NOTIFY_PARTY_3_TYPE']"
ACI_NVOCC = "x://*[@id='ACI_FF']"

VGM_TOGGLE = "x://*[@id='checkVGM']"
VGM_RESPONSIBLE_PARTY = "x://*[@id='ebi1_txt_respons_party']"
VGM_AUTHORIZED_PERSON = "x://*[@id='ebi1_txt_auth_name']"
CONTAINER_GROUPS = "x://*[@class='Group']/table[1]/tbody/tr/td/div/div"
DELETE_CONTAINER_TOGGLE = (
    "x://*[@id='groupList']/div/table/tbody/tr/td[2]/div/table/tbody/tr/td/div/"
    "div[1]/table/tbody/tr/td[1]/input[2]"
)
DELETE_CONTAINER_BUTTON = "x://*[@name='delCntr']"
ADD_CONTAINER_BUTTON = "x://*[@name='addCntr']"
VGM_BOOKING_SELECTS = "x://*[@name='ebi1_sel_vgm_bkno']"
TOTAL_MARKS = "x://*[@name='shippingMarks']"
TOTAL_GOODS_DESCRIPTION = "x://*[@name='cargoDesp']"
HS_CODE = "x://*[@id='EBI1_HTS_CODE']"
MORE_HS_CODE_BUTTON = "x://*[@id='ebi1_more_hts_modalbox']"
MORE_HS_CODE_CONFIRM = "x://*[@id='MB_content']/div/input[1]"

FILING_AT = "x://*[@id='filingType_end']"
FILING_BY = "x://*[@id='filingType_carrier']"
FILING_SINGLE = "x://*[@id='refData_single']"
FILING_MULTIPLE = "x://*[@id='refData_multi']"
FILING_HOUSE_BILL = "x://*[@id='refData_house']"
SUPPLEMENTARY_DECLARANT = "x://*[@id='eoriNo_end']"
CUSTOMS_CODE = "x://*[@id='cusCode']"
MORE_CUSTOMS_CODE = "x://*[@beforesubmit='showMoreCusCode']"
ADD_SEQUENCE = "x://*[@id='addSeq']"
MORE_CONTAINER_ROWS = "x://*[@id='moreCntrNo']//tbody/tr"
MORE_CONTAINER_CONFIRM = "x://*[@id='MB_content']/div//input[1]"

BL_NATURE = "x://*[@id='BL_NATURE']"
RECEIPT_SHIPMENT = "x://*[@id='RCV_SHIPMENT']"
EMAIL_RELEASE = "x://*[@id='EMAIL_RELEASE']"
ISSUE_PLACE_BUTTON = "x://*[@id='ebi1_Issueplace_Img']"
PAYABLE_PLACE_BUTTON = "x://*[@id='ebi1_PAYABLE_PLACE_Img']"
BOOKING_PLACE_BUTTON = "x://*[@id='BOOKING_OFC']/../span/img"
LOCATION_WORDING_TAB = "x://*[@id='blutSingleWordingDiv']/a"
LOCATION_COUNTRY = "x://*[@id='countryRecords']"
LOCATION_CITY = "x://*[@id='locRecords']"
LOCATION_SUBMIT = "x://*[@id='blut_single_location_submit']"
TRANSPORT_MODE = "x://*[@id='SVC_TYPE']"
TRANSPORT_TERM = "x://*[@id='SVC_MODE']"
NUMBER_OF_ORIGINAL = "x://*[@id='OBL_NO_FRT']"
NUMBER_OF_COPY = "x://*[@id='BLCOPY_NO_FRT']"
NUMBER_OF_ORIGINAL_WITH_FREIGHT = "x://*[@id='OBL_WITH_FRT']"
NUMBER_OF_COPY_WITH_FREIGHT = "x://*[@id='BLCOPY_WITH_FRT']"

CONTACT_PERSON = "x://*[@id='EBI1_CONTACT_PERSON']"
PHONE_COUNTRY_CODE = "x://*[@id='EBI1_TEL_CTRY']"
PHONE_AREA_CODE = "x://*[@id='EBI1_TEL_ZIP']"
PHONE_NUMBER = "x://*[@id='EBI1_TEL']"
PHONE_EXTENSION = "x://*[@id='EBI1_TEL_EXT']"
NOTIFY_EMAIL = "x://*[@id='EBI1_NTFY_EMAIL']"
MORE_EMAIL_TOGGLE = "x://*[@id='EBI1_MORE_EMAIL']"
SECOND_EMAIL = "x://*[@id='EBI1_MORE_EMAIL_1']"
THIRD_EMAIL = "x://*[@id='EBI1_MORE_EMAIL_2']"
REMARKS = "x://*[@id='remarks']"
NOTIFY_EMAIL_BUTTON = "x://*[@id='EBI1_NTFY_EMAIL']"

SUBMIT_BUTTON = "x://*[@id='EBI1_btnApply']"
SAVE_DRAFT_BUTTON = "x://*[@id='EBI1_btnDraft']"


def by_id(element_id: str) -> str:
    """返回 EMC 静态 id 元素的定位器。"""
    return f"x://*[@id='{element_id}']"


def otp_input(index: int) -> str:
    return by_id(f"tam1_opt_number_{index}")


def container_field(index: int, row: int, column: int, suffix: str = "") -> str:
    """返回旧 EMC 表格中一个集装箱基础区字段。"""
    return (
        f"x://div[{index}]/table/tbody/tr/td[2]/table[1]/tbody/tr[{row}]/td[{column}]"
        f"{suffix}"
    )


def container_input(index: int, row: int, column: int) -> str:
    return container_field(index, row, column, "/input")


def container_select(index: int, row: int, column: int) -> str:
    return container_field(index, row, column, "/select")


def container_seal(index: int, seal_index: int) -> str:
    return (
        f"x://div[{index}]/table/tbody/tr/td[2]/table[1]/tbody/tr[6]"
        f"//td/input[{seal_index}]"
    )


def vgm_field(index: int, column: int, suffix: str) -> str:
    return f"x://div[{index}]/table/tbody/tr/td[2]/table[2]/tbody/tr[2]/td[{column}]{suffix}"


def additional_hs_code(index: int) -> str:
    return by_id(f"ebi1_HtCode{index}")


def customs_code(index: int) -> str:
    return by_id(f"cusCode{index}")


def sequence_select(index: int, row: int, column: int) -> str:
    return f"x://*[@id='seq{index}']/tbody/tr[{row}]/td[{column}]/table/tbody/tr[1]/td/select"


def sequence_eori_input(index: int, row: int, column: int) -> str:
    return f"x://*[@id='seq{index}']/tbody/tr[{row}]/td[{column}]/table/tbody/tr[1]/td/input"


def sequence_row_input(index: int, row: int, column: int) -> str:
    return f"x://*[@id='seq{index}']/tbody/tr[{row}]/td[{column}]/table/tbody/tr[8]/td/input"


def sequence_commodity_toggle(index: int, commodity_index: int) -> str:
    return by_id(f"seq{index}_commToggle{commodity_index}") + "/input"


def sequence_commodity_rows(index: int, commodity_index: int) -> str:
    return by_id(f"seq{index}_commToggle{commodity_index}") + "/table[1]/tbody/tr"


def sequence_commodity_field(index: int, commodity_index: int, field_id: str) -> str:
    return by_id(f"seq{index}_{field_id}{commodity_index}")
