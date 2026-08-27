# Research: Running and Deploying Tiny LLMs on Google Cloud

## Overview
This document explores how to locally run and efficiently host small LLMs on Google Cloud for simple tasks. These patterns align with Hackathon strategies prioritizing ease of deployment, cost-efficiency, and leveraging Google Cloud services.

## 1. Local Execution of Small Models (Gemma)
The Gemma family (e.g., Gemma 2B, Gemma 3, Gemma 4) provides highly efficient open models that can be run on modest hardware (like laptops with 8GB+ RAM) without dedicated GPUs. 

**Using Ollama (Recommended)**
Ollama is the easiest tool for locally managing and serving models.
- **Install:** Download from [Ollama.com](https://ollama.com/download)
- **Run Gemma (v2, 2B):** `ollama run gemma2:2b`
- **Run Gemma (v1, 2B):** `ollama run gemma:2b`
- Upon execution, Ollama automatically downloads the weights (~1.6GB for the 2B version) and starts an interactive chat session.
*Primary Sources:* [Ollama Model Library](https://ollama.com/library/gemma2), [Google Developer Docs](https://ai.google.dev/gemma).

## 2. Deploying on Google Cloud
For hackathons, serverless and managed endpoints are the most efficient choices to host your models.

### Option A: Cloud Run (Cost-Efficient, Serverless)
Cloud Run allows you to deploy containerized LLMs and scales to zero when not in use, making it highly cost-efficient.
- **Easiest Path:** Use **Google AI Studio** to select a Gemma model and click "Deploy to Cloud Run." This builds and configures a container natively supporting the Google Gen AI SDK.
- **Custom Containerization (Advanced):** You can package a model using inference frameworks like **Ollama** or **vLLM**. Ollama often provides faster cold starts as the model weights are baked into the container image. vLLM provides higher performance and allows for mounting weights via Cloud Storage (FUSE).
- **Hardware Configuration:** Configure the Cloud Run service to use NVIDIA L4 GPUs to significantly boost inference speed. Ensure adequate VRAM (e.g., Gemma 4 31B dense variant requires 16GB-71GB depending on quantization).
*Primary Sources:* [Google Cloud Run Docs](https://cloud.google.com/run/docs), [Google Codelabs - vLLM on Cloud Run](https://codelabs.developers.google.com/).

### Option B: Vertex AI Model Garden (Managed Endpoints)
For production-grade scalability or minimal infrastructure management, Vertex AI is a powerful option.
- **One-Click Deploy:** Navigate to the Vertex AI Model Garden, select the Gemma model, and use the "Deploy" feature to provision compute resources to a dedicated Vertex AI endpoint.
- **Programmatic Deployment:** Utilize the Vertex AI Python SDK (`aiplatform.Endpoint.create()`), specifying the serving container (like vLLM or Hugging Face TGI), and deploy it to a dedicated endpoint with specific machine types and GPUs.
*Primary Sources:* [Vertex AI Open Models](https://cloud.google.com/vertex-ai/docs/generative-ai/open-models/use-gemma).

## 3. Managed Alternatives: Gemini APIs
For simple tasks where managing infrastructure (even Cloud Run) is overkill, using the Gemini API directly is the most lightweight and cost-effective approach.
- **Gemini Flash (3.5 / 3.7):** Designed specifically for high-speed, cost-efficient inference, perfect for hackathons where API keys can simply be used directly.
*Primary Sources:* [Google AI for Developers](https://ai.google.dev/).
