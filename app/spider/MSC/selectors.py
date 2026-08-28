"""MSC myMSC 登录页定位器。"""

LOGIN_URL = "https://www.mymsc.com/myMSC/"
AUTH_URL = "https://mscciam.b2clogin.com/mscciam.onmicrosoft.com/oauth2/v2.0/authorize"
INDEX_URL = "https://www.mymsc.com/myMSC/welcome"

# myMSC 首屏先收集邮箱，再跳转到 Azure AD B2C 密码页。
LOGIN_USERNAME = "c:#UserName"
LOGIN_NEXT = "c:button.nxt-btn"
IDENTITY_USERNAME = "c:#signInName"
IDENTITY_PASSWORD = "c:#password"
IDENTITY_SUBMIT = "c:#next"
IDENTITY_ERROR_MESSAGES = "c:#api .error p"
COOKIE_ACCEPT_BUTTON = "c:#onetrust-accept-btn-handler"


EBOOKINGS_URL ="https://www.mymsc.com/myMSC/dashboard/ebookings"
DASHBOARD_GRAPHQL_API = "https://services.mymsc.com/dashboard/graphql"
BOOKING_SEARCH_INPUT = "c:.textSearchContainer input"
SEARCH_BUTTON = "c:.searchBar+button"
BOOKING_FIRST_NUMBER = "c:.MuiDataGrid-virtualScrollerRenderZone>div:nth-child(1) .bknumber"
BOOKING_FIRST_STATUS = "c:.MuiDataGrid-virtualScrollerRenderZone>div:nth-child(1) .MuiGrid-item:nth-child(3)"
BOOKING_FIRST_BUTTON = "c:.MuiDataGrid-virtualScrollerRenderZone>div:nth-child(1) .buttons-container-responsive .responsive"

SHIPPING_INSTRUCTIONS_URL = "https://www.mymsc.com/myMSC/shippinginstructions/shippinginstructions"

SI_SHADOW = "c:#eSi-app"
SELECT_DOCUMENT_RADIO = "c:[data-testid=document-selection] label"
DOCUMENT_TYPE_RADIO = "c:[data-testid=rbOrigin] label"
UNFREIGHTED_NUM = "c:[data-testid=qtyOriginalUnfreighted] input"
FREIGHTED_NUM = "c:[data-testid=qtyOriginalFreighted] input"
REQUESTED_COPIES_UNFREIGHTED = "c:[data-testid=chkCopyUnfreighted] input"
REQUESTED_COPIES_FREIGHTED = "c:[data-testid=chkCopyFreighted] input"
COPIES_UNFREIGHTED_NUM = "c:[data-testid=qtyCopyUnfreighted] input"
COPIES_FREIGHTED_NUM = "c:[data-testid=qtyCopyFreighted] input"

SHIPPER_EDIT_BUTTON = "x://h5[contains(text(),'Shipper')]/button"
FORWARD_EDIT_BUTTON = "x://h5[contains(text(),'Forwarding Agency')]/button"
DIALOG_NAME = "c:.party-edit-wrapper [name=name]"
DIALOG_ADDRESS_DETAILS= "c:.party-edit-wrapper [name=address]"
DIALOG_TITLE = "c:.party-edit-wrapper [name='billOfLadingData.name']"
DIALOG_ADDRESS = "c:.party-edit-wrapper [name='billOfLadingData.address']"
DIALOG_CONTACT_REFERENCE = "c:.party-edit-wrapper [name='billOfLadingData.contact']"
DIALOG_LOCATION = "c:.party-edit-wrapper [name=location]"
DIALOG_LOCATION_OPTION = "c:.MuiAutocomplete-listbox li"


DIALOG_CONTACT_NAME = "c:.party-edit-wrapper [name=contactName]"
DIALOG_CONTACT_PHONE = "c:.party-edit-wrapper [name=contactPhone]"
DIALOG_CONTACT_FAX = "c:.party-edit-wrapper [name=contactFax]"
DIALOG_CONTACT_EMAIL = "c:.party-edit-wrapper [name=contactEmail]"
DIALOG_SAVE_BTN = "c:.party-edit-wrapper [data-testid=btnSavePartyEdit]"

ADD_NEW_PARTY_BUTTON = "c:#AddNewParty"

RECEIPT_INPUT = "c:[data-testid=textFieldLocation-ORIGIN]  input"
POL_INPUT = "c:[data-testid=textFieldLocation-POL]  input"
POD_INPUT = "c:[data-testid=textFieldLocation-POD]  input"
DELIVERY_INPUT = "c:[data-testid=textFieldLocation-DESTINATION]  input"


