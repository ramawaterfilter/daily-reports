import unittest

import main


class TransformOrdersTest(unittest.TestCase):
    def test_native_csv_format_and_continuation_row(self):
        order = {
            "id": "gid://shopify/Order/123",
            "name": "#1",
            "email": "buyer@example.com",
            "createdAt": "2026-10-08T03:26:44Z",
            "displayFinancialStatus": "PAID",
            "displayFulfillmentStatus": "UNFULFILLED",
            "currencyCode": "GBP",
            "customer": {
                "defaultEmailAddress": {"marketingState": "SUBSCRIBED"},
            },
            "billingAddress": {
                "address1": "Unit 1",
                "address2": "High Street",
                "province": "England",
                "provinceCode": "ENG",
                "country": "United Kingdom",
                "countryCodeV2": "GB",
            },
            "subtotalPriceSet": {"shopMoney": {"amount": "39"}},
            "totalShippingPriceSet": {"shopMoney": {"amount": "6"}},
            "totalTaxSet": {"shopMoney": {"amount": "7.5"}},
            "totalPriceSet": {"shopMoney": {"amount": "45"}},
            "totalDiscountsSet": {"shopMoney": {"amount": "0"}},
            "totalRefundedSet": {"shopMoney": {"amount": "0"}},
            "totalOutstandingSet": {"shopMoney": {"amount": "0"}},
            "taxLines": [{
                "title": "GB VAT",
                "rate": 0.2,
                "priceSet": {"shopMoney": {"amount": "7.5"}},
            }],
            "lineItems": {"nodes": [
                {
                    "id": "line-1",
                    "quantity": 1,
                    "name": "Product",
                    "sku": "SKU-1",
                    "vendor": "Vendor",
                    "requiresShipping": True,
                    "taxable": True,
                    "originalUnitPriceSet": {"shopMoney": {"amount": "39"}},
                    "totalDiscountSet": {"shopMoney": {"amount": "0"}},
                    "variant": {"compareAtPrice": "49"},
                },
                {
                    "id": "line-2",
                    "quantity": 1,
                    "name": "Free item",
                    "sku": "SKU-2",
                    "vendor": "Vendor",
                    "requiresShipping": True,
                    "taxable": True,
                    "originalUnitPriceSet": {"shopMoney": {"amount": "0"}},
                    "totalDiscountSet": {"shopMoney": {"amount": "0"}},
                    "variant": {},
                },
            ]},
        }

        rows = [dict(zip(main.SHEET_HEADERS, row)) for row in main.transform_orders([order])]

        self.assertEqual(rows[0]["Subtotal"], "39.00")
        self.assertEqual(rows[0]["Tax 1 Name"], "GB VAT 20%")
        self.assertEqual(rows[0]["Tax 1 Value"], "7.50")
        self.assertEqual(rows[0]["Billing Street"], "Unit 1, High Street")
        self.assertEqual(rows[0]["Billing Province"], "ENG")
        self.assertEqual(rows[0]["Billing Country"], "GB")
        self.assertEqual(rows[0]["Id"], "123")
        self.assertEqual(rows[0]["Lineitem compare at price"], "49.00")
        self.assertEqual(rows[0]["Lineitem fulfillment status"], "pending")
        self.assertEqual(rows[1]["Name"], "#1")
        self.assertEqual(rows[1]["Email"], "buyer@example.com")
        self.assertEqual(rows[1]["Created at"], "2026-10-08 04:26:44 +0100")
        self.assertEqual(rows[1]["Subtotal"], "")
        self.assertEqual(rows[1]["Tax 1 Name"], "")

        original_exclusions = main.EXCLUDED_LINEITEM_SKUS
        try:
            main.EXCLUDED_LINEITEM_SKUS = {"sku-1"}
            filtered_rows = [
                dict(zip(main.SHEET_HEADERS, row))
                for row in main.transform_orders([order])
            ]
        finally:
            main.EXCLUDED_LINEITEM_SKUS = original_exclusions

        self.assertEqual(len(filtered_rows), 1)
        self.assertEqual(filtered_rows[0]["Lineitem sku"], "SKU-2")
        self.assertEqual(filtered_rows[0]["Subtotal"], "39.00")


if __name__ == "__main__":
    unittest.main()
