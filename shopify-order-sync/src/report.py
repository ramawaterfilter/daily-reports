from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

QUERY = """
query GetOrders($first: Int!, $after: String, $query: String) {
    orders(
        first: $first
        after: $after
        query: $query
        sortKey: CREATED_AT
        reverse: false
    ) {
        nodes {
            id
            name
            createdAt
            updatedAt
            cancelledAt
            processedAt

            email
            phone
            note
            tags
            sourceName
            currencyCode

            displayFinancialStatus
            displayFulfillmentStatus

            subtotalPriceSet {
                shopMoney {
                    amount
                    currencyCode
                }
            }

            totalPriceSet {
                shopMoney {
                    amount
                    currencyCode
                }
            }

            totalTaxSet {
                shopMoney {
                    amount
                    currencyCode
                }
            }

            totalShippingPriceSet {
                shopMoney {
                    amount
                    currencyCode
                }
            }

            totalDiscountsSet {
                shopMoney {
                    amount
                    currencyCode
                }
            }

            totalOutstandingSet {
                shopMoney {
                    amount
                    currencyCode
                }
            }

            totalRefundedSet {
                shopMoney {
                    amount
                    currencyCode
                }
            }

            customer {
                firstName
                lastName
                defaultEmailAddress {
                    emailAddress
                    marketingState
                }
                defaultPhoneNumber {
                    phoneNumber
                }
            }

            billingAddress {
                name
                address1
                address2
                company
                city
                zip
                province
                provinceCode
                country
                countryCodeV2
                phone
            }

            shippingAddress {
                name
                address1
                address2
                company
                city
                zip
                province
                provinceCode
                country
                countryCodeV2
                phone
            }

            shippingLines(first: 20) {
                nodes {
                    title
                    code

                    originalPriceSet {
                        shopMoney {
                            amount
                            currencyCode
                        }
                    }
                }
            }

            discountCodes

            customAttributes {
                key
                value
            }

            lineItems(first: 100) {
                nodes {
                    id
                    name
                    title
                    quantity
                    requiresShipping
                    taxable
                    sku
                    vendor

                    originalUnitPriceSet {
                        shopMoney {
                            amount
                            currencyCode
                        }
                    }

                    discountedUnitPriceSet {
                        shopMoney {
                            amount
                            currencyCode
                        }
                    }

                    totalDiscountSet {
                        shopMoney {
                            amount
                            currencyCode
                        }
                    }

                    taxLines {
                        title
                        rate

                        priceSet {
                            shopMoney {
                                amount
                                currencyCode
                            }
                        }
                    }

                    variant {
                        id
                        sku
                        compareAtPrice

                        product {
                            vendor
                        }
                    }
                }
            }

            fulfillments {
                id
                status
                createdAt
                updatedAt

                location {
                    id
                    name
                }

                fulfillmentLineItems(first: 100) {
                    nodes {
                        id
                        quantity

                        lineItem {
                            id
                        }
                    }
                }
            }

            transactions {
                id
                kind
                status
                gateway
                createdAt
                processedAt
                paymentId
                receiptJson

                amountSet {
                    shopMoney {
                        amount
                        currencyCode
                    }
                }
            }

            paymentGatewayNames

            paymentTerms {
                id
                paymentTermsName
                paymentTermsType
                dueInDays

                paymentSchedules(first: 20) {
                    nodes {
                        id
                        dueAt
                        issuedAt
                        completedAt

                        balanceDue {
                            amount
                            currencyCode
                        }

                        totalBalance {
                            amount
                            currencyCode
                        }
                    }
                }
            }

            risk {
                assessments {
                    riskLevel

                    provider {
                        title
                    }
                }

                recommendation
            }

            retailLocation {
                id
                name
            }

            taxLines {
                title
                rate

                priceSet {
                    shopMoney {
                        amount
                        currencyCode
                    }
                }
            }
        }

        pageInfo {
            hasNextPage
            endCursor
        }
    }
}
"""
SHEET_HEADERS = [
    "Name",
    "Email",
    "Financial Status",
    "Paid at",
    "Fulfillment Status",
    "Fulfilled at",
    "Accepts Marketing",
    "Currency",
    "Subtotal",
    "Shipping",
    "Taxes",
    "Total",
    "Discount Code",
    "Discount Amount",
    "Shipping Method",
    "Created at",
    "Lineitem quantity",
    "Lineitem name",
    "Lineitem price",
    "Lineitem compare at price",
    "Lineitem sku",
    "Lineitem requires shipping",
    "Lineitem taxable",
    "Lineitem fulfillment status",
    "Billing Name",
    "Billing Street",
    "Billing Address1",
    "Billing Address2",
    "Billing Company",
    "Billing City",
    "Billing Zip",
    "Billing Province",
    "Billing Country",
    "Billing Phone",
    "Shipping Name",
    "Shipping Street",
    "Shipping Address1",
    "Shipping Address2",
    "Shipping Company",
    "Shipping City",
    "Shipping Zip",
    "Shipping Province",
    "Shipping Country",
    "Shipping Phone",
    "Notes",
    "Note Attributes",
    "Cancelled at",
    "Payment Method",
    "Payment Reference",
    "Refunded Amount",
    "Vendor",
    "Outstanding Balance",
    "Employee",
    "Location",
    "Device ID",
    "Id",
    "Tags",
    "Risk Level",
    "Source",
    "Lineitem discount",
    "Tax 1 Name",
    "Tax 1 Value",
    "Tax 2 Name",
    "Tax 2 Value",
    "Tax 3 Name",
    "Tax 3 Value",
    "Tax 4 Name",
    "Tax 4 Value",
    "Tax 5 Name",
    "Tax 5 Value",
    "Phone",
    "Receipt Number",
    "Duties",
    "Billing Province Name",
    "Shipping Province Name",
    "Payment ID",
    "Payment Terms Name",
    "Next Payment Due At",
    "Payment References",
]

def money_value(money_set):
    if not money_set:
        return ""

    shop_money = money_set.get("shopMoney")

    if not shop_money:
        return ""

    amount = shop_money.get("amount")

    if amount in (None, ""):
        return ""

    try:
        return f"{Decimal(str(amount)):.2f}"
    except InvalidOperation:
        return str(amount)


def format_amount(amount):
    if amount in (None, ""):
        return ""

    try:
        return f"{Decimal(str(amount)):.2f}"
    except InvalidOperation:
        return str(amount)


def format_shopify_datetime(value, store_timezone="Europe/London"):
    if not value:
        return ""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(ZoneInfo(store_timezone)).strftime(
        "%Y-%m-%d %H:%M:%S %z"
    )


def numeric_id(value):
    return value.rsplit("/", 1)[-1] if value else ""


def format_street(address):
    return ", ".join(
        part for part in [address.get("address1"), address.get("address2")]
        if part
    )


def format_tax_name(tax_line):
    title = tax_line.get("title") or ""
    rate = tax_line.get("rate")

    if not title or rate in (None, ""):
        return title

    percentage = Decimal(str(rate)) * 100
    percentage_text = format(percentage, "f").rstrip("0").rstrip(".")
    return f"{title} {percentage_text}%"


def format_payment_gateway(gateway):
    names = {
        "shopify_payments": "Shopify Payments",
        "paypal": "PayPal Express Checkout",
    }
    return names.get(gateway, gateway.replace("_", " ").title())


def get_lineitem_sku(line_item):
    variant = line_item.get("variant") or {}
    return line_item.get("sku") or variant.get("sku") or ""


# def get_full_name(first_name, last_name):
#     return " ".join(
#         part for part in [first_name, last_name]
#         if part
#     )


def format_note_attributes(attributes):
    if not attributes:
        return ""

    return "\n".join(
        f"{item.get('key', '')}: {item.get('value', '')}"
        for item in attributes
    )


def format_tags(tags):
    if not tags:
        return ""

    return ", ".join(tags)


def get_successful_transaction(order):
    transactions = order.get("transactions") or []

    for transaction in transactions:
        if (
            transaction.get("status") == "SUCCESS"
            and transaction.get("kind") in ["SALE", "CAPTURE"]
        ):
            return transaction

    return None


def get_paid_at(order, store_timezone="Europe/London"):
    transaction = get_successful_transaction(order)

    if transaction:
        paid_at = transaction.get("createdAt") or transaction.get("processedAt")
        if paid_at:
            created_at = order.get("createdAt")
            return format_shopify_datetime(max(paid_at, created_at or paid_at), store_timezone)

    return ""


def get_payment_method(order):
    gateways = order.get("paymentGatewayNames") or []

    if gateways:
        return ", ".join(format_payment_gateway(gateway) for gateway in gateways)

    transactions = order.get("transactions") or []

    gateways = [
        transaction.get("gateway")
        for transaction in transactions
        if transaction.get("gateway")
    ]

    return ", ".join(
        format_payment_gateway(gateway)
        for gateway in dict.fromkeys(gateways)
    )


def get_payment_id(order):
    transactions = order.get("transactions") or []

    payment_ids = [
        transaction.get("paymentId")
        for transaction in transactions
        if transaction.get("paymentId")
    ]

    return ", ".join(dict.fromkeys(payment_ids))


def get_payment_reference(order):
    transactions = order.get("transactions") or []

    references = []

    for transaction in transactions:
        payment_id = transaction.get("paymentId")

        if payment_id:
            references.append(payment_id)

    return ", ".join(dict.fromkeys(references))

# def get_receipt_number(order):
#     transactions = order.get("transactions") or []

#     for transaction in transactions:
#         if transaction.get("status") != "SUCCESS":
#             continue

#         receipt_json = transaction.get("receiptJson")

#         if not receipt_json:
#             continue

#         # Shopify may return this as a dict/object
#         if isinstance(receipt_json, dict):
#             return json.dumps(
#                 receipt_json,
#                 separators=(",", ":")
#             )

#         # If already a string
#         return str(receipt_json)

#     return ""


def get_fulfilled_at(order, store_timezone="Europe/London"):
    fulfillments = order.get("fulfillments") or []

    dates = [
        fulfillment.get("createdAt")
        for fulfillment in fulfillments
        if fulfillment.get("createdAt")
    ]

    return format_shopify_datetime(min(dates), store_timezone) if dates else ""


def get_lineitem_fulfillment_status(order, line_item_id):
    fulfillments = order.get("fulfillments") or []

    fulfilled_quantity = 0

    for fulfillment in fulfillments:
        fulfillment_status = fulfillment.get("status")

        if fulfillment_status not in ["SUCCESS", "OPEN"]:
            continue

        fulfillment_items = (
            fulfillment.get("fulfillmentLineItems") or {}
        ).get("nodes", [])

        for fulfillment_item in fulfillment_items:
            line_item = fulfillment_item.get("lineItem") or {}

            if line_item.get("id") == line_item_id:
                fulfilled_quantity += (
                    fulfillment_item.get("quantity") or 0
                )

    if fulfilled_quantity > 0:
        return "fulfilled"

    return "pending"

def get_payment_terms(order):
    payment_terms = order.get("paymentTerms")

    if not payment_terms:
        return "", ""

    payment_terms_name = (
        payment_terms.get("paymentTermsName") or ""
    )

    schedules = (
        payment_terms.get("paymentSchedules") or {}
    ).get("nodes", [])

    # Find the next payment schedule that is not completed
    upcoming_due_dates = []

    for schedule in schedules:
        if schedule.get("completedAt"):
            continue

        due_at = schedule.get("dueAt")

        if due_at:
            upcoming_due_dates.append(due_at)

    next_payment_due_at = ""

    if upcoming_due_dates:
        next_payment_due_at = min(upcoming_due_dates)

    return payment_terms_name, next_payment_due_at

def transform_orders(orders, store_timezone="Europe/London", excluded_skus=frozenset()):
    rows = []

    for order in orders:

        customer = order.get("customer") or {}

        billing = order.get("billingAddress") or {}
        shipping = order.get("shippingAddress") or {}

        line_items = (
            order.get("lineItems") or {}
        ).get("nodes", [])
        line_items = [
            line_item for line_item in line_items
            if get_lineitem_sku(line_item).casefold() not in excluded_skus
        ]

        shipping_lines = (
            order.get("shippingLines") or {}
        ).get("nodes", [])

        shipping_methods = []

        for line in shipping_lines:
            title = line.get("title")

            if title and title not in shipping_methods:
                shipping_methods.append(title)

        shipping_method = ", ".join(shipping_methods)

        discount_codes = order.get("discountCodes") or []

        discount_code = ", ".join(discount_codes)

        note_attributes = format_note_attributes(
            order.get("customAttributes")
        )

        transaction = get_successful_transaction(order)

        payment_reference = get_payment_reference(order)
        payment_id = get_payment_id(order)
        # receipt_number = get_receipt_number(order)

        payment_method = get_payment_method(order)

        payment_terms_name, next_payment_due_at = get_payment_terms(order)

        fulfilled_at = get_fulfilled_at(order, store_timezone)

        tags = format_tags(order.get("tags"))

        risk_level = ""

        risk = order.get("risk") or {}
        assessments = risk.get("assessments") or []

        if assessments:
            risk_level = ", ".join(
                "Low" if assessment.get("riskLevel") == "NONE"
                else (assessment.get("riskLevel") or "").title()
                for assessment in assessments
                if assessment.get("riskLevel")
            )

        location = order.get("retailLocation") or {}

        location_name = location.get("name", "")

        email_consent = customer.get("defaultEmailAddress") or {}
        accepts_marketing = (
            "yes" if email_consent.get("marketingState") == "SUBSCRIBED"
            else "no"
        ) if customer else ""

        # -------------------------------------------------
        # Order-level values
        # -------------------------------------------------

        order_values = {
            "Name": order.get("name",""),

            "Email": order.get("email")
                or (customer.get("defaultEmailAddress") or {}).get("emailAddress")
                or "",

            "Financial Status":
                (order.get("displayFinancialStatus") or "").lower(),

            "Paid at":
                get_paid_at(order, store_timezone),

            "Fulfillment Status":
                (order.get("displayFulfillmentStatus") or "").lower(),

            "Fulfilled at":
                fulfilled_at,

            "Accepts Marketing":
                accepts_marketing,

            "Currency":
                order.get("currencyCode") or "",

            "Subtotal":
                money_value(order.get("subtotalPriceSet")),

            "Shipping":
                money_value(order.get("totalShippingPriceSet")),

            "Taxes":
                money_value(order.get("totalTaxSet")),

            "Total":
                money_value(order.get("totalPriceSet")),

            "Discount Code":
                discount_code,

            "Discount Amount":
                money_value(order.get("totalDiscountsSet")),

            "Shipping Method":
                shipping_method,

            "Created at":
                format_shopify_datetime(order.get("createdAt"), store_timezone),

            "Billing Name":
                billing.get("name") or "",

            "Billing Street":
                format_street(billing),

            "Billing Address1":
                billing.get("address1") or "",

            "Billing Address2":
                billing.get("address2") or "",

            "Billing Company":
                billing.get("company") or "",

            "Billing City":
                billing.get("city") or "",

            "Billing Zip":
                billing.get("zip") or "",

            "Billing Province":
                billing.get("provinceCode") or "",

            "Billing Country":
                billing.get("countryCodeV2") or "",

            "Billing Phone":
                billing.get("phone") or "",

            "Shipping Name":
                shipping.get("name") or "",

            "Shipping Street":
                format_street(shipping),

            "Shipping Address1":
                shipping.get("address1") or "",

            "Shipping Address2":
                shipping.get("address2") or "",

            "Shipping Company":
                shipping.get("company") or "",

            "Shipping City":
                shipping.get("city") or "",

            "Shipping Zip":
                shipping.get("zip") or "",

            "Shipping Province":
                shipping.get("provinceCode") or "",

            "Shipping Country":
                shipping.get("countryCodeV2") or "",

            "Shipping Phone":
                shipping.get("phone") or "",

            "Notes":
                order.get("note") or "",

            "Note Attributes":
                note_attributes,

            "Cancelled at":
                format_shopify_datetime(order.get("cancelledAt"), store_timezone),

            "Payment Method":
                payment_method,

            "Payment Reference":
                payment_reference,

            "Refunded Amount":
                money_value(order.get("totalRefundedSet")),

            "Outstanding Balance":
                money_value(order.get("totalOutstandingSet")),

            "Employee":
                "",

            "Location":
                location_name,

            "Device ID":
                "",

            "Id":
                numeric_id(order.get("id")),

            "Tags":
                tags,

            "Risk Level":
                risk_level,

            "Source":
                order.get("sourceName") or "",

            "Phone":
                order.get("phone")
                or (customer.get("defaultPhoneNumber") or {}).get("phoneNumber")
                or "",

            # "Receipt Number":
            #     receipt_number,

            # "Duties":
            #     "",

            "Billing Province Name":
                billing.get("province") or "",

            "Shipping Province Name":
                shipping.get("province") or "",

            "Payment ID":
                payment_id,

            "Payment Terms Name":
                payment_terms_name,

            "Next Payment Due At":
                format_shopify_datetime(next_payment_due_at, store_timezone),

            "Payment References":
                payment_reference,
        }

        # -------------------------------------------------
        # One Google Sheet row per line item
        # -------------------------------------------------

        order_tax_lines = order.get("taxLines") or []

        for index, line_item in enumerate(line_items):

            variant = line_item.get("variant") or {}

            product = variant.get("product") or {}

            line_item_discount = money_value(
                line_item.get("totalDiscountSet")
            )

            line_item_fulfillment_status = (
                get_lineitem_fulfillment_status(
                    order,
                    line_item.get("id"),
                )
            )

            repeated_values = {
                "Name": order_values["Name"],
                "Email": order_values["Email"],
                "Created at": order_values["Created at"],
            }

            row = {
                **(order_values if index == 0 else repeated_values),

                "Lineitem quantity":
                    line_item.get("quantity") or 0,

                "Lineitem name":
                    line_item.get("name") or "",

                "Lineitem price":
                    money_value(
                        line_item.get("originalUnitPriceSet")
                    ),

                "Lineitem compare at price":
                    format_amount(variant.get("compareAtPrice")),

                "Lineitem sku":
                    get_lineitem_sku(line_item),

                "Lineitem requires shipping":
                    str(bool(line_item.get("requiresShipping"))).lower(),

                "Lineitem taxable":
                    str(bool(line_item.get("taxable"))).lower(),

                "Lineitem fulfillment status":
                    line_item_fulfillment_status,

                "Vendor":
                    line_item.get("vendor")
                    or product.get("vendor")
                    or "",

                "Lineitem discount":
                    line_item_discount,

            }

            if index == 0:
                for tax_index, tax_line in enumerate(order_tax_lines[:5], 1):
                    row[f"Tax {tax_index} Name"] = format_tax_name(tax_line)
                    row[f"Tax {tax_index} Value"] = money_value(
                        tax_line.get("priceSet")
                    )

            rows.append(
                [row.get(header, "") for header in SHEET_HEADERS]
            )

    return rows
