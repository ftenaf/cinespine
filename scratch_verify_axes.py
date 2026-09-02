import asyncio
import os
from backend.app.script.parser import parse_fountain_screenplay
from backend.app.script.character_ai import enrich_screenplay_characters

async def main():
    print("USE VERTEX:", os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"))
    print("API KEY:", bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")))
    
    with open("/app/data/examples/demo_script.fountain", "r", encoding="utf-8") as f:
        script = f.read()
    
    screenplay = parse_fountain_screenplay(script, title="DEMO")
    print("Parsed characters:", len(screenplay.characters))
    
    screenplay = await enrich_screenplay_characters(screenplay)
    
    print("\nWarnings:")
    for w in screenplay.parse_warnings:
        print(" -", w)
        
    print("\nCharacters:")
    for c in screenplay.characters:
        axes = c.personality_axes
        if not axes:
            print(f"{c.name}: NO AXES SCORED")
        else:
            print(f"{c.name}: Axes Scored! {len(axes)}")

if __name__ == "__main__":
    asyncio.run(main())
