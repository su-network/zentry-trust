# Zentry-Trust

Zero Trust wrapper for apps using OpenZiti. Makes your services invisible (no public port) - only authorized identities can access them.

<img width="1358" height="131" alt="image" src="https://github.com/user-attachments/assets/8cac55cd-df4d-4ba2-8441-0c6e262df6dc" />


## Quick Start

**Clone Repository**
```bash
git clone https://github.com/su-network/zentry-trust.git
```

**Navigate to Directory**
```bash
cd zentry-trust
```

**Install Package**
```bash
pip install -e .
```

**Launch Everything**
```bash
zentry u
```

Open http://localhost:8080/ in your browser.



## 🔌 Ports

- **1280** - Controller API (management & config)
- **1408** - ZAC admin console → http://localhost:1408/ (admin/admin)
- **3022** - Edge router (internal fabric)
- **8080** - Local proxy for browser access
- **NONE** - Your ghost app (completely dark!)


Licensed under Apache-2.0 |
> Copyright 2025 Zentry-Trust Contributors
