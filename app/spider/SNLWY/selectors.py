"""SNLWY  登录页定位器。"""

from app.spider.MSCGW.selectors import POD_INPUT


LOGIN_URL = "https://ibs.sinolines.com/#/login"
INDEX_URL = "https://ibs.sinolines.com/#/search-service/quick-search"
INDEX_API_URL = "https://ibs.sinolines.com/admin-api/system/fileManage/page"

LOGIN_API_URL = "http://115.236.42.234:42000/interface/api/mscgw/login"
ATTACHMENT_API_URL = "http://115.236.42.234:42000/interface//api/mscgw/get_attachment"

# myMSC 首屏先收集邮箱，再跳转到 Azure AD B2C 密码页。
LOGIN_USERNAME = "x://*[contains(@class, 'login-form')]//input[@placeholder='请输入用户名']"
LOGIN_PASSWORD = "x://*[contains(@class, 'login-form')]//input[@type='password']"
LOGIN_SUBMIT = "x://*[contains(@class, 'login-form')]//*[contains(@class, 'submit-btn')]//button"
LOGIN_TAG_DOM = "x://*[contains(@class, 'user-info')]//button[normalize-space()='登录']"  # 是否登录标识

BOOKING_URL =  "https://ibs.sinolines.com/#/export/booking"
BOOKING_LIST_API = "https://ibs.sinolines.com/admin-api/system/soManage/pageSo"

DIALOG_CANCEL_BTN= "x://*[contains(@class,'el-dialog__body')]//button[normalize-space(.)='取消']"
# 查询类型当前展示为「订舱号」时，真正的输入节点在同一组右侧。
BOOKING_SEARCH_INPUT = (
    "x://*[contains(@class,'base-query__group-container')]"
    "[.//*[contains(@class,'el-select__placeholder')][normalize-space()='订舱号']]"
    "//*[contains(@class,'base-query__group-field--last')]//input[contains(@class,'el-input__inner')]"
)
SEARCH_BUTTON = "x://*[contains(@class,'query-condition')]//button[normalize-space()='查询']"
BOOKING_ROW = "c:.cmg-grid__body-rows>div:nth-child(1)"
BOOKING_ROW_NO = "c:.cmg-grid__body-rows>div:nth-child(1) .booking-no button"
# OPEN_BL_NO_BTN = "x://*[contains(@class,'cmg-grid__body-rows')]/div[1]//*[contains(@class,'action-bar')]/div[normalize-space()='生成提单' and not(contains(concat(" ",normalize-space(@class)," "),' disabled '))]"
# OPEN_BL_NO_BTN = "x://*[contains(@class,'cmg-grid__body-rows')]/div[1]//*[contains(@class,'action-bar')]/div[normalize-space()='生成提单']"
OPEN_BL_NO_BTN = "x://*[contains(@class,'cmg-grid__body-rows')]/div[1]//*[contains(@class,'action-bar')]/div[normalize-space()='生成提单' and not(contains(@class,'disabled'))]"
BOOKING_CHECK_API = "https://ibs.sinolines.com/admin-api/system/soAmendApply/checkOperation"
CREATE_BL_URL = "https://ibs.sinolines.com/#/export/lading/create"

RECEIPT_TEXT = "x://*[contains(@class,'header-container')]//*[contains(@class,'spe-item')][contains(normalize-space(),'接货地')]//*[contains(@class,'el-form-item__content')]/div//*[contains(@class,'form-value')]"
POL_TEXT = "x://*[contains(@class,'header-container')]//*[contains(@class,'spe-item')][contains(normalize-space(),'装货港')]//*[contains(@class,'el-form-item__content')]/div//*[contains(@class,'form-value')]"
POD_TEXT = "x://*[contains(@class,'header-container')]//*[contains(@class,'spe-item')][contains(normalize-space(),'卸货港')]//*[contains(@class,'el-form-item__content')]/div//*[contains(@class,'form-value')]"
DELIVERY_TEXT = "x://*[contains(@class,'header-container')]//*[contains(@class,'spe-item')][contains(normalize-space(),'目的地')]//*[contains(@class,'el-form-item__content')]/div//*[contains(@class,'form-value')]"

RECEIPT_EDIT = "x://*[contains(@class,'header-container')]//*[contains(@class,'spe-item')][contains(normalize-space(),'接货地')]//*[contains(@class,'edit-action')]"
POL_EDIT = "x://*[contains(@class,'header-container')]//*[contains(@class,'spe-item')][contains(normalize-space(),'装货港')]//*[contains(@class,'edit-action')]"
POD_EDIT = "x://*[contains(@class,'header-container')]//*[contains(@class,'spe-item')][contains(normalize-space(),'卸货港')]//*[contains(@class,'edit-action')]"
DELIVERY_EDIT = "x://*[contains(@class,'header-container')]//*[contains(@class,'spe-item')][contains(normalize-space(),'目的地')]//*[contains(@class,'edit-action')]"

PORT_SELECT = "x://*[contains(@class,'el-popper')][not(contains(@style,'display: none'))][contains(normalize-space(),'修改描述')]//input[contains(@class,'el-select__input')]"
PORT_OPTIONS = "x://*[contains(@class,'el-popper')][not(contains(@style,'display: none')) and not(contains(@style,'display:none'))]//ul/li"
PORT_SUBMIT = "x://*[contains(@class,'el-popper')][not(contains(@style,'display: none')) and not(contains(@style,'display:none'))]//button[normalize-space()='确定']"

RELEASE_MODE_SELECT = "c:.sign-order .el-select__wrapper"
RELEASE_MODE_OPTIONS = "x://*[contains(@class,'el-popper')][not(contains(@style,'display: none')) and not(contains(@style,'display:none'))]//*[contains(@class,'sign-type-option')]/div"
# 选中后 input.value 仍为空，真正的展示在 placeholder 里，例如 T、电放、签发 1 份。
RELEASE_MODE_TEXT = "c:.sign-order .el-select__placeholder"
HBL_NO = "x://*[contains(@class,'el-form-item__label')][normalize-space()='House B/L No.']/following-sibling::*[1]//input"


def customer_info_selector(section: str, label: str, part: str, from_parent: bool = False) -> str:
    """按 区块名、字段标签、子元素路径 构造客户信息区块选择器。

    part 为 following-sibling 内的 XPath 片段，例如：
    - 文本内容: "*[contains(@class,'cm-content')]"
    - 清除按钮: "*[contains(@class,'textarea-clear-icon')]"
    - 复选框: "label[normalize-space()='提单中显示']"
    from_parent 为 True 时，从 label 的父元素（表单项）的相邻元素开始查找。
    """
    anchor = "//*[contains(@class,'el-form-item__label')]" f"[normalize-space()='{label}']"
    if from_parent:
        anchor += "/parent::*/following-sibling::*[1]"
    else:
        anchor += "/following-sibling::*[1]"
    return (
        "x://*[contains(@class,'customer-info')]"
        f"[contains(normalize-space(),'{section}')]"
        + anchor
        + f"//{part}"
    )

COUNTRY_OPTIONS = "x://*[contains(@class,'el-popper')][not(contains(@style,'display: none')) and not(contains(@style,'display:none'))]//ul/li/div/span[1]"


def cargo_content_selector(label: str, part: str) -> str:
    """按货物信息标签定位 .cargo-content 内的输入节点。

    先匹配 el-form-item__label 文本，再取相邻内容节点，最后定位 part。
    part 为 following-sibling 内的 XPath 片段，例如：
    - 富文本: "*[contains(@class,'cm-content')]"
    - 清除按钮: "*[contains(@class,'textarea-clear-icon')]"
    - 文本域: "*[contains(@class,'el-textarea__inner')]"
    - 下拉输入: "*[contains(@class,'el-select__input')]"
    - 数字输入: "*[contains(@class,'el-input__inner')]"
    """
    return (
        "x://*[contains(@class,'cargo-content')]"
        f"//*[contains(@class,'el-form-item__label')][normalize-space()='{label}']"
        "/following-sibling::*[1]"
        f"//{part}"
    )


def cargo_content_text_selector(label: str) -> str:
    """定位货物信息里没有输入框、只展示文本的表单项，例如包装代码。"""
    return (
        "x://*[contains(@class,'cargo-content')]"
        f"//*[contains(@class,'el-form-item__label')][normalize-space()='{label}']"
        "/following-sibling::*[contains(@class,'el-form-item__content')]"
    )


HS_CODE_OPTIONS = (
    "x://*[contains(@class,'el-popper')][contains(@class,'hscode-select')]"
    "[not(contains(@style,'display: none')) and not(contains(@style,'display:none'))]"
    "//li[contains(@class,'el-select-dropdown__item')]"
)

ADD_CONTAINER_BTN = "x://*[contains(@class,'container-title__actions')]//button[normalize-space()='添加箱']"
CONTAINER_DIALOG = "c:.si-container-modal"
CNTR_TAB = "c:#tab-CNTR"
VGM_TAB = "c:#tab-VGM"
DIALOG_ADD_CONTAINER_BTN = "c:.si-container-modal .add-cntr-btn"
DIALOG_CONFIRM_BTN = "x://*[contains(@class,'si-container-modal')]//button[normalize-space()='确定添加']"
DIALOG_VGM_BTN = "x://*[contains(@class,'si-container-modal')]//button[contains(normalize-space(),'添加 VGM')]"
CONTAINER_TYPE_MISMATCH_CONTINUE = (
    "x://*[contains(@class,'el-message-box')][contains(@class,'container-no-match-box')]"
    "//button[normalize-space()='继续']"
)


def container_dialog_selector(label: str, part: str) -> str:
    """按添加箱弹窗里的字段标签定位输入节点。"""
    return (
        "x://*[contains(@class,'si-container-modal')]"
        f"//*[contains(@class,'el-form-item__label')][normalize-space()='{label}']"
        "/following-sibling::*[1]"
        f"//{part}"
    )


def container_row_selector(container_no: str) -> str:
    """定位箱详情表中包含指定箱号的行。

    箱列表不在 #pane-CNTR 内，页签节点是空的，表格在 .cntr-card 里。
    """
    return (
        "x://*[contains(@class,'cntr-card')]"
        "//*[contains(@class,'el-table__body-wrapper')]"
        "//*[contains(@class,'el-table__body')]"
        f"//tr[contains(normalize-space(),'{container_no}')]"
    )
ELEMENT_SELECT_OPTIONS = "x://*[contains(@class,'el-popper')][not(contains(@style,'display: none')) and not(contains(@style,'display:none'))]//ul/li"
SECOND_NOTIFY_CHECK = "x://*[contains(@class,'customer-info')]//label[normalize-space()='第二通知人']"
TO_ORDER_CHECK = "x://*[contains(@class,'customer-info')][contains(normalize-space(),'收货人信息')]//label[normalize-space()='TO ORDER']"
SAMEASCONSIGNEE_CHECK = "x://*[contains(@class,'customer-info')][contains(normalize-space(),'通知人信息')]//label[normalize-space()='SAME AS CONSIGNEE']"


def requirement_group_selector(group: str) -> str:
    """定位提单页某一组要求。装船、订舱、货物要求都用 booking-req-group。"""
    return (
        "x://*[contains(@class,'si-detail')]"
        "//*[contains(@class,'booking-req-group')]"
        f"[./*[contains(@class,'group-title')][normalize-space()='{group}']]"
    )


def requirement_checkbox_selector(group: str, option: str) -> str:
    """按组标题和选项文本定位复选框 label。

    真正的 input 没有尺寸，不能点。含电池在订舱要求和货物要求里各有一个，
    必须先限定到对应组。
    """
    return (
        requirement_group_selector(group)
        + f"//label[contains(@class,'el-checkbox')][normalize-space()='{option}']"
    )


def requirement_option_selector(group: str) -> str:
    """定位某一组要求里的全部复选框 label。"""
    return (
        requirement_group_selector(group)
        + "//label[contains(@class,'el-checkbox')]"
    )


def requirement_checked_selector(group: str) -> str:
    """定位某一组要求里已勾选的复选框 label。"""
    return (
        requirement_group_selector(group)
        + "//label[contains(@class,'el-checkbox') and contains(@class,'is-checked')]"
    )


SURCHARGE_ROWS = (
    "x://*[contains(@class,'summary-col')]"
    "[.//span[contains(normalize-space(),'运费及附加费')]]"
    "//*[contains(@class,'el-table__body-wrapper')]"
    "//tbody/tr"
)


def surcharge_row_selector(index: int) -> str:
    """按表格从上到下的序号定位运费及附加费行，index 从 0 开始。"""
    return (
        "x://*[contains(@class,'summary-col')]"
        "[.//span[contains(normalize-space(),'运费及附加费')]]"
        "//*[contains(@class,'el-table__body-wrapper')]"
        f"//tbody/tr[{index + 1}]"
    )


def surcharge_payment_selector(index: int) -> str:
    """指定付款方式。点外层 el-select，不点没有尺寸的 input。"""
    return (
        surcharge_row_selector(index)
        + "//*[contains(@class,'el-select--default')]"
    )


def surcharge_print_selector(index: int) -> str:
    """是否打印。第一行没有这个复选框。"""
    return surcharge_row_selector(index) + "//label[contains(@class,'el-checkbox')]"


ATTACHMENT_ADD = "x://*[contains(@class,'additional-attach')]//*[contains(@class,'add-box')]"
ATTACHMENT_LIST = "x://*[contains(@class,'additional-attach')]//*[contains(@class,'attachment-list')]"
UPLOAD_DIALOG = "c:.upload-dialog"
UPLOAD_TYPE_SELECT = "x://*[contains(@class,'upload-dialog')]//*[contains(@class,'el-select--default')]"
UPLOAD_TYPE_OPTIONS = (
    "x://*[contains(@class,'el-popper')]"
    "[not(contains(@style,'display: none')) and not(contains(@style,'display:none'))]"
    "//li[contains(@class,'el-select-dropdown__item')]"
)
UPLOAD_FILE_DRAGGER = "x://*[contains(@class,'upload-dialog')]//*[contains(@class,'el-upload-dragger')]"
UPLOAD_CONFIRM = (
    "x://*[contains(@class,'upload-dialog')]"
    "//button[normalize-space()='确定' and not(contains(@class,'is-disabled'))]"
)


def notification_email_selector(part: str) -> str:
    """定位接收通知邮箱。标签里带必填星号，用包含匹配。"""
    return (
        "x://*[contains(@class,'tag-input-popover-row')]"
        "[.//*[contains(@class,'el-form-item__label')][contains(normalize-space(),'接收通知邮箱')]]"
        f"//{part}"
    )

SAVE_BUTTON = "x://button[normalize-space()='存为草稿']"
SUBMIT_BUTTON = "x://button[normalize-space()='提交']"
ATTACH_BUTTON = "x://button[normalize-space()='预览件']"

