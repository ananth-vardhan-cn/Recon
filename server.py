import os
import asyncio
import shutil
from fastapi import FastAPI, WebSocket, UploadFile, File, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import google.generativeai as genai
from src.tools import Tools

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.0-flash-exp")

app = FastAPI()

# CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (uploaded images) so frontend can verify crops
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

if not GEMINI_API_KEY or not TAVILY_API_KEY:
    print("Error: Please set GEMINI_API_KEY and TAVILY_API_KEY in .env")
    # Note: In a server context, we might not want to exit, but we should warn

genai.configure(api_key=GEMINI_API_KEY)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_location = f"static/{file.filename}"
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"file_path": file_location, "url": f"/static/{file.filename}"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Helper to send logs to frontend
    async def send_log(message: str, type="log"):
        await websocket.send_json({"type": type, "content": message})

    try:
        while True:
            try:
                # 1. Wait for initialization data (image path)
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                print("Client disconnected while waiting for input.")
                break
            except Exception:
                 break

            image_path = data.get("file_path")

            if not image_path or not os.path.exists(image_path):
                await send_log("File not found.", "error")
                continue

            # Initialize Tools
            tools_handler = Tools(TAVILY_API_KEY)

            # Upload Initial Image
            await send_log(f"--- Recon (Powered by {MODEL_NAME}) ---", "system")
            await send_log("Loading image...", "system")
            current_file = await asyncio.to_thread(genai.upload_file, path=image_path, display_name="GeoTarget")
            await send_log(f"Image uploaded: {current_file.display_name}", "system")

            # Define Tool Functions (as expected by the model)
            def web_search(query: str):
                """Performs a web search to verify location clues."""
                return tools_handler.web_search(query)

            def crop_image(box_ymin: int, box_xmin: int, box_ymax: int, box_xmax: int):
                """
                Crops the original image to investigate a specific area (zoom in).
                Args:
                    box_ymin, box_xmin, box_ymax, box_xmax: Coordinates for the crop box.
                """
                # We use the path from the outer scope variable 'image_path'
                # Note: box in PIL is (left, top, right, bottom) -> (xmin, ymin, xmax, ymax)
                return tools_handler.crop_image(image_path, [box_xmin, box_ymin, box_xmax, box_ymax])

            tools_list = [web_search, crop_image]

            model = genai.GenerativeModel(
                model_name=MODEL_NAME,
                tools=tools_list,
                system_instruction="""
You are an expert Geolocalization Agent.
Your goal: Determine the precise location of the input image.

Follow this strict, systematic reasoning process (The Enhanced Recon Method):

2. **VISUAL DATA EXTRACTION** (Systematically catalog visible elements):
   - Text Elements: Street names, shop names, billboards, license plates, signs in all languages/scripts
   - Brand Logos: Banks, finance companies, retail chains, petrol stations, telecommunications
   - Vehicles: Auto-rickshaws, buses, trucks, cars with regional characteristics, license plate formats
   - Architecture: Building styles, roof types, construction materials, color schemes
   - Infrastructure: Road markings, traffic signs, pole styles, street lighting, utility lines
   - Environment: Vegetation types, sun position/shadows, weather indicators
   - People: Clothing styles, crowd density, cultural indicators
   - Objects: Specific items that indicate region (e.g., produce sacks, goods, tools)

3. **GEOGRAPHIC TRIANGULATION** (Connect data points to narrow location):
   - Combine multiple visual cues to infer region/type of location (e.g., busy market street + auto-rickshaws + Tamil script = Tamil Nadu city)
   - Identify unique combinations of features that pinpoint specific areas (e.g., specific bank + jewelry shop + market trucks in known pattern)
   - Use environmental context (e.g., wholesale market trucks suggest commercial district)

4. **VERIFICATION & CROSS-REFERENCE** (Use tools to confirm hypotheses):
   - Search for specific businesses, landmarks, or text with geographic context
   - Verify that combinations of features exist in the same location
   - Check for stock photo or known images if pattern looks familiar

5. **HYPOTHESIS REFINEMENT** (Update based on tool results):
   - Incorporate search results to refine location estimates
   - Adjust regional hypothesis based on confirmation of specific landmarks
   - Use negative results to eliminate possibilities

6. **PRECISION LOCALIZATION** (Identify exact location):
   - Use specific addresses, intersections, or landmarks for pinpoint accuracy
   - Consider the angle and perspective of the image to identify the exact vantage point

**CRITICAL TERMINATION RULE:**
- If you have found the location, you MUST output a detailed report in the following format and then type **[STOP]**:

  **FINAL GEOLOCATION REPORT**
  *   **Feature Name:** [Name of building, intersection, landmark, etc.]
  *   **Address:** [Full street address, City, Region, Country]
  *   **Context:** [Route number, highway name, or nearby landmarks]
  *   **Coordinates:** [Latitude, Longitude]
  *   **Google Maps Link:** https://www.google.com/maps/search/?api=1&query=[Lat],[Long]
  *   **Verification Summary:** [Brief summary of key visual cues and verification steps that confirmed this location]

- If you determine it is IMPOSSIBLE (e.g., generic stock photo with no specific markers), explain why and type **[STOP]**.
- Do not repeat yourself. If you have no new tools to run and cannot make further progress, type **[STOP]**.

**Important:**
- When using `crop_image`, specify the box coordinates carefully based on the image size (assume 1000x1000 relative if unsure, or best guess).
- You are an Agent. You must CALL TOOLS to verify, especially for specific businesses, landmarks, or text that could confirm location.
- Prioritize specific, searchable elements (like business names, street signs, license plates) over general visual features.
- Always consider the geographic and cultural context of visual elements.
"""
    )

            # Start Chat WITHOUT automatic function calling (we handle it manually for file uploads)
            chat = model.start_chat(enable_automatic_function_calling=False)

            # Initial Prompt
            prompt_parts = [current_file, "Geolocate this image. Use tools to verify clues."]

            process_completed = False  # Flag to track if process is completed

            # Simulation Loop (Limit 10 turns)
            for turn in range(10):
                if process_completed:
                    break

                await send_log(f"\n--- Turn {turn + 1} ---", "turn_start")

                try:
                    # Run blocking model call in thread
                    response = await asyncio.to_thread(chat.send_message, prompt_parts)

                    # Reset prompt_parts for the next turn (default to continue)
                    prompt_parts = ["Proceed."]
                    tool_called = False

                    # Iterate through parts to handle text and function calls
                    for part in response.parts:
                        # 1. Text Response
                        if part.text:
                            text = part.text
                            await send_log(f"[Agent]: {text}", "agent_thought")

                            # STOP CONDITIONS
                            text_lower = text.lower()
                            if "[stop]" in text_lower:
                                await send_log("\n[Process Completed - Stop Signal Received]", "system")
                                process_completed = True
                                break
                            if "final answer" in text_lower and "coordinates" in text_lower:
                                await send_log("\n[Process Completed - Final Answer Found]", "system")
                                process_completed = True
                                break
                            if "impossible" in text_lower and "stock photo" in text_lower:
                                await send_log("\n[Process Completed - Unable to Geolocate]", "system")
                                process_completed = True
                                break

                        # 2. Function Call
                        if fn := part.function_call:
                            tool_called = True
                            # Convert MapComposite to a standard dict for readable printing
                            args_dict = dict(fn.args)
                            await send_log(f"[Tool Call]: {fn.name}({args_dict})", "tool_call")

                            # EXECUTE TOOL
                            tool_result = None

                            if fn.name == "web_search":
                                query = fn.args.get("query", "")
                                tool_result = await asyncio.to_thread(tools_handler.web_search, query)
                                # Feed back text result
                                prompt_parts = [
                                    genai.protos.Part(
                                        function_response=genai.protos.FunctionResponse(
                                            name="web_search",
                                            response={"result": tool_result}
                                        )
                                    )
                                ]
                                await send_log(f"[Tool Result]: {str(tool_result)[:200]}...", "tool_result")

                            elif fn.name == "crop_image":
                                try:
                                    # Extract args (safely handle potential missing keys or types)
                                    ymin = int(fn.args.get("box_ymin", 0))
                                    xmin = int(fn.args.get("box_xmin", 0))
                                    ymax = int(fn.args.get("box_ymax", 100))
                                    xmax = int(fn.args.get("box_xmax", 100))

                                    new_crop_path = await asyncio.to_thread(tools_handler.crop_image, image_path, [xmin, ymin, xmax, ymax])
                                    await send_log(f"[Tool Action]: Cropped image saved to {new_crop_path}", "tool_result")

                                    # UPLOAD NEW FILE
                                    crop_file = await asyncio.to_thread(genai.upload_file, path=new_crop_path, display_name="ZoomedCrop")

                                    # Send URL to frontend for display
                                    relative_path = f"/static/{os.path.basename(new_crop_path)}"
                                    await websocket.send_json({"type": "new_image", "url": relative_path})

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
                                    await send_log(f"Crop Error: {e}", "error")
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
                    await send_log(f"Error in loop: {e}", "error")
                    # Detailed debug
                    try:
                        await send_log(f"Raw candidate: {response.candidates[0]}", "error")
                    except:
                        pass
                    break

            await send_log("\nAgent ready for new task.", "system")
            await websocket.send_json({"type": "session_end", "content": "Session Concluded. Ready for next target."})

    except Exception as e:
        print(f"WebSocket Error: {e}")