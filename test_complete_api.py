import requests
import json
import time

API_URL = "http://localhost:8000"

print("="*60)
print("TESTING COMPLETE SMARTRECEIPT API")
print("="*60)

# Test 1: Upload first receipt
print("\n1️⃣ Uploading receipt 1...")
with open("../test_images/receipt3.jpg", "rb") as f:
    files = {"file": ("receipt3.jpg", f, "image/jpeg")}
    response = requests.post(f"{API_URL}/upload", files=files)

if response.status_code == 200:
    receipt1 = response.json()
    print(f"✅ Receipt 3 saved! ID: {receipt1['id']}")
    print(f"   Merchant: {receipt1['merchant_name']}")
    print(f"   Total: ${receipt1['total']}")
else:
    print(f"❌ Error: {response.json()}")
    exit(1)

time.sleep(2)

# # Test 2: Upload second receipt (if you have another image)
# print("\n2️⃣ Uploading receipt 2...")
# try:
#     with open("../test_images/receipt3.jpg", "rb") as f:
#         files = {"file": ("receipt2.jpg", f, "image/jpeg")}
#         response = requests.post(f"{API_URL}/upload", files=files)
    
#     if response.status_code == 200:
#         receipt2 = response.json()
#         print(f"✅ Receipt 2 saved! ID: {receipt2['id']}")
#     else:
#         print(f"⚠️  Could not upload receipt 2")
# except:
#     print("⚠️  No second receipt found, skipping")

# time.sleep(1)

# Test 3: Get all receipts
print("\n3️⃣ Getting all receipts...")
response = requests.get(f"{API_URL}/receipts")
receipts = response.json()
print(f"✅ Found {len(receipts)} receipt(s)")
for r in receipts:
    print(f"   - ID {r['id']}: {r['merchant_name']} - ${r['total']}")

# Test 4: Get specific receipt
print(f"\n4️⃣ Getting receipt ID {receipt1['id']}...")
response = requests.get(f"{API_URL}/receipts/{receipt1['id']}")
receipt = response.json()
print(f"✅ Retrieved receipt:")
print(f"   Merchant: {receipt['merchant_name']}")
print(f"   Items: {len(receipt['items'])}")
for item in receipt['items']:
    print(f"     - {item['name']}: ${item['price']}")

# Test 5: Get analytics
print("\n5️⃣ Getting analytics...")
response = requests.get(f"{API_URL}/analytics")
analytics = response.json()
print(f"✅ Analytics:")
print(f"   Total Receipts: {analytics['total_receipts']}")
print(f"   Total Spent: ${analytics['total_spent']}")
print(f"   By Category:")
for category, amount in analytics['by_category'].items():
    print(f"     - {category}: ${amount:.2f}")

# Test 6: Get categories
print("\n6️⃣ Getting categories...")
response = requests.get(f"{API_URL}/categories")
categories = response.json()
print(f"✅ Available categories: {', '.join(categories['categories'])}")

# Test 7: Filter by category
print("\n7️⃣ Filtering by category 'groceries'...")
response = requests.get(f"{API_URL}/receipts?category=groceries")
grocery_receipts = response.json()
print(f"✅ Found {len(grocery_receipts)} grocery receipt(s)")

print("\n" + "="*60)
print("✅ ALL TESTS PASSED!")
print("="*60)