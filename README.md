# 🌸 Sadaf Agent

**Sadaf Agent** is an autonomous, real-time Voice & Vision AI companion designed for seamless conversation, multi-file memory management, dynamic tool dispatching, and intelligent model routing.

---

## ✨ Features

- 🎙️ **Real-Time Voice Assistant**: Low-latency Speech-to-Text via Whisper (Groq) with Voice Activity Detection (VAD) and fast macOS TTS output.
- 👁️ **Vision Intelligence**: Camera tool integration supporting visual scene understanding and multimodal query handling.
- 🧠 **Multi-File Memory System**: Autonomous memory agent that extracts, stores, and consolidates facts, user preferences, emotions, career, health, and sessions.
- ⚡ **Multi-Key Groq Load Balancer**: Efficient API key pool rotator ensuring maximum quota throughput and zero rate-limit downtime.
- 🔀 **Smart Model Router**: Dynamically routes simple queries to `llama-3.1-8b-instant` and complex reasoning/emotional queries to `llama-3.3-70b-versatile`.
- 🛠️ **Extensive Tool Suite**:
  - Web Search (Tavily & GNews integration)
  - Application Launcher & Navigation
  - System Info & Volume Control
  - Screenshot & Camera Tools
  - Date/Time, Timer, Countdown, and Reminders

---

## 📁 Project Structure

```
Sadaf_2/
├── audio/            # Audio capture & playback modules (Listener, Speaker)
├── brain/            # LLM routing & Vision processing engines
├── memory/           # Memory agent, extractor, file store & consolidator
├── tools/            # Modular tools (Web search, camera, system info, etc.)
├── utils/            # General helper utilities
├── config.py         # Central configuration & rate limit tuning
├── groq_proxy.py     # Multi-key proxy load balancer & queue manager
├── listen.py         # Standalone voice listener process
├── speak.py          # Standalone speech synthesizer process
├── main.py           # Core conversational agent entry point
├── personality.py    # System prompt & persona definition
└── requirements.txt  # Project dependencies
```

---

## 🚀 Getting Started

### Prerequisites

- **Python**: 3.10+
- **macOS**: Recommended for native `say` TTS voice capabilities.

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/HamzaDevv/sadaf_agent.git
   cd sadaf_agent
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file in the project root with your API keys:
   ```env
   GROQ_API_KEYS=key1,key2,key3
   GOOGLE_API_KEY=your_google_api_key
   TAVILY_API_KEY=your_tavily_api_key
   GNEWS_API_KEY=your_gnews_api_key
   PRIVACY_MODE=false
   ```

---

## 🏃 Usage

- **Run Voice Agent**:
  ```bash
  python listen.py
  ```

- **Run Core Assistant**:
  ```bash
  python main.py
  ```

---

## 🛡️ Privacy & Security

- Local memory files (`memories/`) and transcriptions (`transcriptions.txt`) are kept strictly on your local device and excluded from version control via `.gitignore`.
- Set `PRIVACY_MODE=true` in `.env` to enforce explicit confirmation before opening the camera.

---

## 📄 License

MIT License. Built with Love and Fun by [HamzaDevv](https://github.com/HamzaDevv).