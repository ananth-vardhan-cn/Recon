import os
from tavily import TavilyClient
from PIL import Image

class Tools:
    def __init__(self, tavily_api_key, log_callback=None):
        self.tavily = TavilyClient(api_key=tavily_api_key)
        self.log_callback = log_callback

    def _log(self, message: str):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    def web_search(self, query: str) -> str:
        """
        Performs a web search using Tavily API to find information about locations, landmarks, or text.
        
        Args:
            query: The search query (e.g., "Rue de la Paix street sign", "vegetation in South Africa").
        
        Returns:
            A string summary of the search results.
        """
        try:
            self._log(f"[Tool: Web Search] Searching for: '{query}'...")
            response = self.tavily.search(query=query, search_depth="advanced")
            results = response.get("results", [])
            
            if not results:
                return "No results found."
            
            # Format results for the LLM
            formatted_results = []
            for res in results[:3]: # Limit to top 3 for conciseness
                formatted_results.append(f"- {res['title']}: {res['content']} ({res['url']})")
            
            return "\n".join(formatted_results)
        except Exception as e:
            return f"Error performing search: {str(e)}"

    def crop_image(self, image_path: str, box: list[int]) -> str:
        """
        Crops an image to a specified bounding box to simulate 'zooming in'.
        
        Args:
            image_path: Path to the original image.
            box: A list of 4 integers [left, top, right, bottom].
        
        Returns:
            Path to the saved cropped image.
        """
        try:
            self._log(f"[Tool: Visual Zoom] Cropping {image_path} to {box}...")
            with Image.open(image_path) as img:
                cropped_img = img.crop(box)
                # Save to a temp file
                base, ext = os.path.splitext(image_path)
                # Create a unique name to avoid overwrites in async context if possible, 
                # but for now keeping simple logic
                output_path = f"{base}_crop_{box[0]}_{box[1]}{ext}"
                cropped_img.save(output_path)
                return output_path
        except Exception as e:
            return f"Error cropping image: {str(e)}"
