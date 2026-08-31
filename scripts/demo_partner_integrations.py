import asyncio
import httpx
import time
from rich.console import Console
from rich.panel import Panel

console = Console()
API_BASE = "http://localhost:8000/api"

async def run_demo():
    console.print(Panel("[bold green]CineSpine Partner Integrations Demo[/bold green]\nGoogle Cloud AI -> ClickHouse -> Grafana"))
    
    async with httpx.AsyncClient() as client:
        # Step 1: Wipe Demo State
        console.print("\n[yellow]1. Wiping previous demo state from ClickHouse...[/yellow]")
        wipe_res = await client.post(f"{API_BASE}/demo/wipe")
        console.print(f"[green]✔ Wipe successful:[/green] {wipe_res.json().get('message')}")
        
        # Step 2: Inject Events (Document AI + ClickHouse Event Spine)
        console.print("\n[yellow]2. Ingesting synthetic Screenplay and TCLog...[/yellow]")
        console.print("   (This triggers Google Cloud Document AI if configured, and streams to ClickHouse)")
        inject_res = await client.get(f"{API_BASE}/events/demo")
        console.print(f"[green]✔ Ingestion successful:[/green] {inject_res.json().get('message')}")
        
        # Wait for async processing
        console.print("[dim]Waiting 5 seconds for dispatcher and reconciler to process events...[/dim]")
        time.sleep(5)
        
        # Step 3: Run Wrap Rescue Agent
        console.print("\n[yellow]3. Running Wrap Rescue Agent (Gemini Flash + ClickHouse MCP)...[/yellow]")
        console.print("   Agent Prompt: 'What discrepancies are we seeing on demo production?'")
        agent_res = await client.get(f"{API_BASE}/wrap-rescue/demo", timeout=30.0)
        resp_data = agent_res.json()
        
        console.print(Panel(
            f"[bold]Agent Response:[/bold]\n{resp_data.get('response')}",
            title="Gemini Output",
            border_style="blue"
        ))
        
        console.print("\n[bold green]Demo Complete![/bold green]")
        console.print("Check Grafana at http://localhost:3000 for telemetry and alerts.")

if __name__ == "__main__":
    asyncio.run(run_demo())
