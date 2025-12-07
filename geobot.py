import os
import google.generativeai as genai
from dotenv import load_dotenv
from src.tools import Tools

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.0-flash-exp")

if not GEMINI_API_KEY or not TAVILY_API_KEY:
    print("Error: Please set GEMINI_API_KEY and TAVILY_API_KEY in .env")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# Initialize Tools
tools_handler = Tools(TAVILY_API_KEY)

def main():
    print(f"--- Recon (Powered by {MODEL_NAME}) ---")
    image_path = input("Enter path to image file: ").strip('"')
    
    if not os.path.exists(image_path):
        print("File not found.")
        return

    # Upload Initial Image
    print("Loading image...")
    current_file = genai.upload_file(path=image_path, display_name="GeoTarget")
    print(f"Image uploaded: {current_file.display_name}", "system")

    # Define Tools
    def web_search(query: str):
        """Performs a web search to verify location clues."""
        return tools_handler.web_search(query)

    def crop_image(box_ymin: int, box_xmin: int, box_ymax: int, box_xmax: int):
        """
        Crops the original image to investigate a specific area (zoom in).
        Args:
            box_ymin, box_xmin, box_ymax, box_xmax: Coordinates for the crop box.
            The model is instructed to use a 1000x1000 coordinate system.
        """
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                width, height = img.size

            # Scale coordinates from 1000x1000 to actual image dimensions
            real_xmin = int((box_xmin / 1000.0) * width)
            real_ymin = int((box_ymin / 1000.0) * height)
            real_xmax = int((box_xmax / 1000.0) * width)
            real_ymax = int((box_ymax / 1000.0) * height)

            # Basic validation/clamping
            real_xmin = max(0, real_xmin)
            real_ymin = max(0, real_ymin)
            real_xmax = min(width, real_xmax)
            real_ymax = min(height, real_ymax)

            # Ensure box has some size
            if real_xmax <= real_xmin: real_xmax = real_xmin + 1
            if real_ymax <= real_ymin: real_ymax = real_ymin + 1

            # Note: box in PIL is (left, top, right, bottom) -> (xmin, ymin, xmax, ymax)
            return tools_handler.crop_image(image_path, [real_xmin, real_ymin, real_xmax, real_ymax])
        except Exception as e:
            return f"Error calculating crop coordinates: {str(e)}"

    tools_list = [web_search, crop_image]

    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        tools=tools_list,
        system_instruction="""
You are an expert Geolocalization Agent.
Your goal: Determine the precise location of the input image.

 Follow this strict reasoning process (The Recon Method):                                                                                                                         │
 1. **Observation:** deeply analyze the image. Look for:                                                                                                                             │
    - Text: Street signs, license plates, shop names (crucial!).                                                                                                                     │
    - Infrastructure: Road markings, traffic lights, pole styles.                                                                                                                    │
    - Nature: Vegetation types, sun position (shadows), soil color.                                                                                                                  │
    - Architecture: Roof styles, window shapes, materials.

 2. **Hypothesis Generation:** Formulate a theory about the region or country.

 3. **Verification (Action):**                                                                                                                                                       │
    - Use the `web_search` tool to verify specific text, phone numbers, or unique landmarks.                                                                                         │
    - Do NOT guess. If you see a shop name "Chez Pierre", search for it combined with other visible clues.                                                                           │
    - If you see a phone number, search for the area code.

 4. **Refinement:** Update your hypothesis based on tool outputs.

 5. **Final Answer:** Output the final latitude and longitude in a structured format.

**CRITICAL TERMINATION RULE:**
- If you have found the location, you MUST output a detailed report in the following format and then type **[STOP]**:

  **FINAL GEOLOCATION REPORT**
  *   **Feature Name:** [Name of building, bridge, park, etc.]
  *   **Address:** [Full street address, City, Region, Country]
  *   **Context:** [Route number, highway name, or nearby landmarks]
  *   **Coordinates:** [Latitude, Longitude]
  *   **Google Maps Link:** https://www.google.com/maps/search/?api=1&query=[Lat],[Long]

- If you determine it is IMPOSSIBLE (e.g., generic stock photo), explain why and type **[STOP]**.
- Do not repeat yourself. If you have no new tools to run, type **[STOP]**.

**Important:**
- When using `crop_image`, specify the box coordinates carefully based on the image size (assume 1000x1000 relative if unsure, or best guess).
- You are an Agent. You must CALL TOOLS to verify.
"""
    )

    # Start Chat WITHOUT automatic function calling (we handle it manually for file uploads)
    chat = model.start_chat(enable_automatic_function_calling=False)

    # Initial Prompt
    prompt_parts = [current_file, "Geolocate this image. Use tools to verify clues."]
    
    # Simulation Loop (Limit 10 turns)
    for turn in range(10):
        print(f"\n--- Turn {turn + 1} ---")
        try:
            response = chat.send_message(prompt_parts)
            
            # Reset prompt_parts for the next turn (default to continue)
            prompt_parts = ["Proceed."] 
            tool_called = False

            # Iterate through parts to handle text and function calls
            for part in response.parts:
                # 1. Text Response
                if part.text:
                    print(f"[Agent]: {part.text}")
                    
                    # STOP CONDITIONS
                    text_lower = part.text.lower()
                    if "[stop]" in text_lower:
                        print("\n[Process Completed - Stop Signal Received]")
                        return
                    if "final answer" in text_lower and "coordinates" in text_lower:
                        print("\n[Process Completed - Final Answer Found]")
                        return
                    if "impossible" in text_lower and "stock photo" in text_lower:
                         print("\n[Process Completed - Unable to Geolocate]")
                         return

                # 2. Function Call
                if fn := part.function_call:
                    tool_called = True
                    # Convert MapComposite to a standard dict for readable printing
                    args_dict = dict(fn.args)
                    print(f"[Tool Call]: {fn.name}({args_dict})")
                    
                    # EXECUTE TOOL
                    tool_result = None
                    
                    if fn.name == "web_search":
                        query = fn.args.get("query", "")
                        tool_result = web_search(query)
                        # Feed back text result
                        prompt_parts = [
                            genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name="web_search",
                                    response={"result": tool_result}
                                )
                            )
                        ]
                        print(f"[Tool Result]: {str(tool_result)[:200]}...")

                    elif fn.name == "crop_image":
                        try:
                            # Extract args (safely handle potential missing keys or types)
                            ymin = int(fn.args.get("box_ymin", 0))
                            xmin = int(fn.args.get("box_xmin", 0))
                            ymax = int(fn.args.get("box_ymax", 100))
                            xmax = int(fn.args.get("box_xmax", 100))
                            
                            new_crop_path = crop_image(ymin, xmin, ymax, xmax)
                            print(f"[Tool Action]: Cropped image saved to {new_crop_path}")
                            
                            # UPLOAD NEW FILE
                            crop_file = genai.upload_file(path=new_crop_path, display_name="ZoomedCrop")
                            tool_result = "Image cropped successfully. See the new image attachment."
                            
                            # Feed back the result AND the new file
                            prompt_parts = [
                                genai.protos.Part(
                                    function_response=genai.protos.FunctionResponse(
                                        name="crop_image",
                                        response={"result": tool_result}
                                    )
                                ),
                                crop_file, # <--- THE NEW IMAGE
                                "Here is the zoomed view."
                            ]
                        except Exception as e:
                            print(f"Crop Error: {e}")
                            tool_result = f"Failed to crop: {str(e)}"
                            prompt_parts = [
                                genai.protos.Part(
                                    function_response=genai.protos.FunctionResponse(
                                        name="crop_image",
                                        response={"result": tool_result}
                                    )
                                )
                            ]

            # If no tool call was made and no final answer, we nudge it.
            if not tool_called and not any(part.text and "Final Answer" in part.text for part in response.parts):
                 prompt_parts = ["Please continue. Verify your hypothesis or give the final answer."]

        except Exception as e:
            print(f"Error in loop: {e}")
            # Detailed debug
            try:
                print(f"Raw candidate: {response.candidates[0]}")
            except:
                pass
            break
if __name__ == "__main__":
    main()
