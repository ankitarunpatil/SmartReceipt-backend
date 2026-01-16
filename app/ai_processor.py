import os
import json
from datetime import datetime
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv


class ReceiptProcessor:
    """
    FREE receipt processing using Gemini 2.5 Flash (Vision-capable)
    """

    def __init__(self):
        load_dotenv()

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("❌ GEMINI_API_KEY not set")

        genai.configure(api_key=api_key)

        # ✅ CONFIRMED WORKING VISION MODEL
        self.model = genai.GenerativeModel(
            model_name="models/gemini-2.5-flash",
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 2048
            }
        )

        print("✅ Gemini 2.5 Flash initialized (FREE, Vision-enabled)")

    def process_receipt(self, image_path: str) -> dict:
        prompt = """
        Analyze this receipt image and return ONLY valid JSON:

        {
            "merchant_name": "Store name",
            "date": "YYYY-MM-DD",
            "items": [
                {
                    "name": "Item name",
                    "quantity": 1,
                    "price": 0.00
                }
            ],
            "subtotal": 0.00,
            "tax": 0.00,
            "total": 0.00,
            "category": "groceries"
        }

        Rules:
        - Numbers must be decimals
        - Category must be one of: groceries, restaurant, gas, shopping, other
        - If date missing, use today
        - Return JSON only, no commentary
        """

        try:
            image = Image.open(image_path).convert("RGB")

            response = self.model.generate_content([prompt, image])

            # Safely extract text
            if hasattr(response, "text") and response.text:
                text = response.text.strip()
            else:
                text = "".join(
                    part.text for part in response.parts if hasattr(part, "text")
                ).strip()

            # Extract JSON block
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end == -1:
                raise ValueError("No JSON found in model output")

            data = json.loads(text[start:end])

            data["success"] = True
            data["processed_at"] = datetime.now().isoformat()
            data["ai_model"] = "gemini-2.5-flash"

            return data

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m app.ai_processor <receipt_image>")
        exit(1)

    image_path = sys.argv[1]

    print("============================================================")
    print("🤖 Processing receipt with Gemini 2.5 Flash (FREE)")
    print("============================================================")

    processor = ReceiptProcessor()
    result = processor.process_receipt(image_path)

    print("\n============================================================")
    print("RECEIPT DATA")
    print("============================================================")
    print(json.dumps(result, indent=2))