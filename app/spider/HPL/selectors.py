"""HPL Shipping Instruction 页面定位器。"""

from app.core.task.errors import BusinessError


SI_URL = "https://www.hapag-lloyd.cn/zh/online-business/documentation/shipping-instructions/shipping-instruction-online.html"
SI_APPLICATION_URL = "https://www.hapag-lloyd.cn/solutions/shipping-instructions/#/"

COOKIE_ACCEPT_BUTTON = "x://*[@id='accept-recommended-btn-handler']"
LOGIN_FORM = "x://*[@form='localAccountForm']"
LOGIN_USERNAME = "x://*[@id='signInName']"
LOGIN_PASSWORD = "x://*[@id='password']"
LOGIN_SUBMIT = "x://*[@id='next']"
SI_PAGE_MARKER = "x://*[text()='Addresses & References']"

BOOKING_SEARCH_INPUT = "x://input[@id='shipping_instruction_online_f:hl12']"
BOOKING_SEARCH_BUTTON = "x://button[@id='shipping_instruction_online_f:hl25']"
BOOKING_SEARCH_RESULT = "x://*[@class='odd']/td[2]/span"
BOOKING_ERROR = "x://*[@id='shipping_instruction_online_f:hl11']"
CONTINUE_BUTTON = "x://*[text()='Continue']"
ASSOCIATED_BL_SELECT = "x://*[@data-testid='associatedBlSelect']"
DROPDOWN_OPTIONS = "x://*[@class='q-virtual-scroll__content']/div"

SHIPPER_INPUT = "x://*[@data-testid='shipperInput']"
SHIPPER_EMAIL_INPUT = "x://*[@data-testid='shipperEmailInput']"
SHIPPER_COUNTRY_INPUT = "x://*[@data-testid='shipperCountryCode']//input"
SHIPPER_PHONE_INPUT = "x://*[@data-testid='shipperPhone']//input"
SHIPPER_REFERENCE_INPUT = "x://*[@data-testid='shippersReferenceInput']"
FORWARDER_REFERENCE_INPUT = "x://*[@data-testid='freightForwardersReferenceInput']"
TO_ORDER_BUTTON = "x://*[text()='To Order']"

CONSIGNEE_INPUT = "x://*[@data-testid='consigneeInput']"
CONSIGNEE_EMAIL_INPUT = "x://*[@data-testid='consigneeEmailInput']"
CONSIGNEE_REFERENCE_INPUT = "x://*[@data-testid='consigneeReferenceInput']"
CONSIGNEE_COUNTRY_INPUT = "x://*[@data-testid='consigneeCountryCode']//input"
CONSIGNEE_PHONE_INPUT = "x://*[@data-testid='consigneePhone']//input"

NOTIFY_INPUT = "x://*[@data-testid='notifyAddressInput']"
NOTIFY_EMAIL_INPUT = "x://*[@data-testid='notifyAddressEmailInput']"
NOTIFY_COUNTRY_INPUT = "x://*[@data-testid='notifyCountryCode']//input"
NOTIFY_PHONE_INPUT = "x://*[@data-testid='notifyPhone']//input"
NOTIFY_ADD_BUTTON = "x://*[@data-testid='notifyAddressAddButton']"

POL_INPUT = "x://*[@aria-label='Port of Loading']"
POD_INPUT = "x://*[@aria-label='Port of Discharge']"

CONTAINERS_SECTION = "x://*[text()='Containers & Cargo']"
DELETE_CONTAINER_BUTTON = "x://*[text()='Delete']"
DELETE_CARGO_BUTTON = "x://*[text()='Delete Cargo Item']"
CONFIRM_BUTTON = "x://*[text()='Confirm']"
ADD_CONTAINER_BUTTON = "x://*[@data-cy='addContainerButton']"
SAME_DESCRIPTION_BUTTON = "x://*[text()='Same description for whole SI']"
TOTAL_NCM_CODE_INPUT = "x://*[@data-testid='ncmCodeInput']"
TOTAL_MARKS_INPUT = "x://*[@data-cy='shippingMarksInput']"
TOTAL_GOODS_DESC_INPUT = "x://*[@data-cy='descriptionOfGoodsInput']"
TOTAL_HS_CODE_INPUT = "x://*[@aria-label='HS Code']"
TOTAL_CHEMICAL_CODE_INPUT = "x://*[@data-cy='ecicsValueInput']"
HS_CODE_OPTIONS = "x://*[@class='text-weight-bold']"

PREPAID_PAYER_SELECT = "x://*[@data-testid='prepaidPayerSelect']"
PREPAID_PAYER_OTHER_INPUT = "x://*[@data-cy='nameAndAddressOfPrepaidPayer']"
COLLECT_PAYER_SELECT = "x://*[@data-testid='collectPayerSelect']"
COLLECT_PAYER_OTHER_INPUT = "x://*[@data-cy='nameAndAddressOfCollectPayer']"
ELSEWHERE_PAYER_INPUT = "x://*[@data-cy='freightPayerInput']"

SEND_BL_DRAFT_INPUT = "x://*[@aria-label='Send first BL Draft to (E-mail):']"
DOCUMENT_TYPE_SELECT = "x://*[@data-cy='documentTypeSelect']"
UNFREIGHTED_ORIGINAL_INPUT = "x://*[@data-cy='unfreightedOriginalBlsInput']"
UNFREIGHTED_COPY_INPUT = "x://*[@data-cy='unfreightedCopies']"
FREIGHTED_ORIGINAL_INPUT = "x://*[@data-cy='freightedOriginalBlsInput']"
FREIGHTED_COPY_INPUT = "x://*[@data-cy='freightedCopies']"
REMARKS_INPUT = "x://*[@aria-label='General comment (Optional)']"

TERMS_CHECKBOX = "x://*[@data-testid='termsCheckbox']/div[1]"
SUBMIT_BUTTON = "x://*[text()='Submit']"
SUBMIT_SUCCESS = "x://*[text()='Your Shipping Instruction has been successfully sent to us.']"
SAVE_DRAFT_BUTTON = "x://*[text()='Save as Draft']"
SAVE_BUTTON = "x://*[text()='Save']"
SAVE_DRAFT_SUCCESS = "x://*[text()='The draft was successfully saved.']"

COUNTRY_REQUIREMENTS_SECTION = "x://*[text()='Country Specific & Customs Requirements']"
ADD_HOUSE_BILL_BUTTON = "x://*[text()='Add House Bill']"
SELF_FILER_USA_INPUT = "x://*[@aria-label='Self Filer SCAC Code']"
SELF_FILER_CAN_INPUT = "x://*[@aria-label='Self filer CAN8000 code']"
SELF_SUPPLEMENTARY_EORI_INPUT = "x://*[@aria-label='EORI No. Self Filer/Supplem. Declarant']"
UCR_NUMBER_INPUT = "x://*[@aria-label='UCR Number']"
SELLER_INPUT = "x://*[@aria-label='  Seller']"
BUYER_INPUT = "x://*[@aria-label='  Buyer']"
SELLER_TAX_ID_INPUT = "x://*[@aria-label='TAX ID of Seller']"
BUYER_TAX_ID_INPUT = "x://*[@aria-label='TAX ID of Buyer']"
SELLER_EORI_INPUT = "x://*[@aria-label='EORI No. of Seller']"
BUYER_EORI_INPUT = "x://*[@aria-label='EORI No. of Buyer']"
CONSIGNEE_EORI_INPUT = "x://*[@aria-label='EORI number for Consignee']"
CONSIGNEE_EORI_SELF_FILER_INPUT = "x://*[@data-testid='eoriConsigneeInput']"
SHIPPER_EORI_INPUT = "x://*[@aria-label='EORI No. of Shipper']"
SHIPPER_EORI_SELF_FILER_INPUT = "x://*[@data-testid='eoriShipperInput']"
FORWARDER_EORI_INPUT = "x://*[@aria-label='EORI No. of Freight Forwarder']"
NOTIFY_EORI_INPUT = "x://*[@aria-label='EORI No. of Notify']"
MANUFACTURER_EORI_INPUT = "x://*[@aria-label='EORI No. of Manufacturer']"
WAREHOUSE_KEEPER_EORI_INPUT = "x://*[@aria-label='EORI No. of Warehouse Keeper']"
CONSOLIDATOR_EORI_INPUT = "x://*[@aria-label='EORI No. of Consolidator']"

CHARGE_OPTION_LABELS = {
    "Prepaid": "Prepaid (Origin)",
    "Collect": "Collect (Destination)",
    "Prepaid (Elsewhere)": "Prepaid (Elsewhere)",
}


def container_locator(index, suffix):
    """返回指定箱号区域内的 XPath 定位器。"""
    return f"x://*[@data-cy='container{index}']{suffix}"


def container_field_locator(index, aria_label):
    """返回指定箱号中带 aria-label 的字段定位器。"""
    return container_locator(index, f"//*[@aria-label='{aria_label}']")


def container_elements_locator(index, suffix):
    """返回指定箱号中可能存在多个元素的 XPath 定位器。"""
    return container_locator(index, suffix)


def charge_option_locator(charge_name, option_label):
    """返回运费项目下指定付款方式的单选框定位器。"""
    return f"x://*[text()='{charge_name} ']//*[@aria-label='{option_label}']"


def charge_option_label(value):
    """将后端付款方式转换为 HPL 页面可识别的单选框标签。"""
    try:
        return CHARGE_OPTION_LABELS[value]
    except KeyError as exc:
        raise BusinessError(f"HPL 不支持的付款方式：{value}") from exc


def additional_notify_input_locator(index):
    """返回第二或第三通知人地址输入框定位器。"""
    label = "  Notify 3 Address (Optional)" if index == 3 else f"  Notify {index} (Optional)"
    return f"x://*[@aria-label='{label}']"


def additional_notify_email_locator(index):
    """返回第二或第三通知人邮箱输入框定位器。"""
    return f"x://*[@data-testid='notifyAddressEmailInput{index}']"


def additional_notify_country_locator(index):
    """返回第二或第三通知人国家区号输入框定位器。"""
    return f"x://*[@data-testid='notify{index}CountryCode']//input"


def additional_notify_phone_locator(index):
    """返回第二或第三通知人电话输入框定位器。"""
    return f"x://*[@data-testid='notify{index}Phone']//input"


def xpath_literal(value):
    """将任意文本转为可嵌入 XPath 的字符串字面量。"""
    value = str(value)
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    quoted_parts = [f"'{part}'" for part in parts]
    return "concat(" + ', "\'", '.join(quoted_parts) + ")"


def text_locator(text):
    """返回与给定文案精确匹配的元素定位器。"""
    return f"x://*[text()={xpath_literal(text)}]"


def container_wood_declaration_locator(index):
    """返回巴西模板箱级木质包装声明下拉框定位器。"""
    return container_locator(index, "//*[@data-testid='woodDeclarationSelect']")


def house_bill_locator(index, suffix):
    """返回指定 House Bill 区域内的 XPath 定位器。"""
    return f"x://*[@data-cy='houseBill{index}']{suffix}"


def house_bill_field_locator(index, aria_label):
    """返回 House Bill 中带 aria-label 的字段定位器。"""
    return house_bill_locator(index, f"//*[@aria-label={xpath_literal(aria_label)}]")


def house_bill_test_id_locator(index, test_id):
    """返回 House Bill 中带 data-testid 的元素定位器。"""
    return house_bill_locator(index, f"//*[@data-testid={xpath_literal(test_id)}]")


def house_bill_placeholder_locator(index, placeholder):
    """返回 House Bill 中带 placeholder 的输入框定位器。"""
    return house_bill_locator(index, f"//*[@placeholder={xpath_literal(placeholder)}]")


def house_bill_text_locator(index, text):
    """返回 House Bill 内与给定文案精确匹配的元素定位器。"""
    return house_bill_locator(index, f"//div[text()={xpath_literal(text)}]")
