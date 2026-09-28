# MathAssistant

**A math tutor that helps you solve problems yourself.** Give it a math problem and it breaks it into steps and asks you questions, one step at a time. It never just gives you the answer.

- Works for any level, from **5 × 5** to **calculus**. It talks to you at the level of the problem.
- Type a problem, write a **word problem**, or add one from a **photo, screenshot, camera, or PDF**, even a whole worksheet.
- Runs **on your own computer** (Windows or Mac). No account with us, no ads, no tracking.
- Uses an AI service (Anthropic's Claude) with **your own key**. You pay the AI company directly for what you use, usually **a few cents per problem**.

---

## Contents

1. [What you need](#what-you-need)
2. [Getting started](#getting-started)
3. [Using MathAssistant](#using-mathassistant)
4. [What does it cost?](#what-does-it-cost)
5. [Privacy](#privacy)
6. [Updating](#updating)
7. [Removing MathAssistant](#removing-mathassistant)
8. [Troubleshooting](#troubleshooting)

---

## What you need

- A **Windows 10/11** PC or a **Mac** (macOS 11 or newer).
- An internet connection.
- A web browser (Chrome, Edge, Firefox, or Safari). MathAssistant opens in your browser, but it runs on your computer.
- An **Anthropic account** with a few dollars of credit, for the AI key. Step 3 below shows how.

You do **not** need to install anything else.

---

## Getting started

### Step 1: Download

Go to the **[latest release](https://github.com/TrevorD90/MathAssistant/releases/latest)** and download the file for your computer:

| Your computer | Download this file |
|---|---|
| Windows 10 or 11 | `MathAssistant-…-windows.zip` |
| Mac with an **Apple** chip (M1, M2, M3, M4…) | `MathAssistant-…-macos-apple-silicon.zip` |
| Mac with an **Intel** chip | `MathAssistant-…-macos-intel.zip` |

> **Which Mac do I have?** Click the  Apple menu (top-left) → **About This Mac**. If it says **Chip: Apple M…**, get *apple-silicon*. If it says **Processor: … Intel …**, get *intel*.

### Step 2: Open it for the first time

MathAssistant is free and isn't "code-signed" (that costs money every year), so the first time you open it, your computer shows a warning. This is expected. You only have to do this once.

#### On Windows

1. Open your **Downloads** folder. **Right-click** the zip file → **Extract All…** → **Extract**.
2. Move the extracted **MathAssistant** folder somewhere you'll find it (for example, your Documents folder).
3. Open the folder and double-click **MathAssistant.exe**.
4. A blue box may say **"Windows protected your PC"**. Click **More info**, then **Run anyway**.
5. A small window saying **"MathAssistant is running"** appears, and MathAssistant opens in your web browser.

> **Tip:** Right-click **MathAssistant.exe** → **Show more options** → **Send to** → **Desktop (create shortcut)** to put a shortcut on your desktop.

#### On a Mac

1. Open your **Downloads** folder and double-click the zip file. It turns into **MathAssistant**.
2. Drag **MathAssistant** into your **Applications** folder.
3. Double-click **MathAssistant** in Applications. You'll see a message that it **"cannot be opened"** or that Apple **"could not verify"** it. Click **Done** (not "Move to Trash").
4. Open  → **System Settings** → **Privacy & Security**. Scroll down to the message about MathAssistant and click **Open Anyway**. Enter your Mac password if asked, then click **Open**.
5. A small window saying **"MathAssistant is running"** appears, and MathAssistant opens in your web browser.

> Later, the Mac may ask whether MathAssistant can use your **keychain** (where it keeps your AI key safely). Enter your Mac password and click **Always Allow**. It may ask again after an update; that's normal.

### Step 3: Get an AI key

MathAssistant uses Anthropic's Claude AI. You need a key, which is like a password that lets MathAssistant use your Anthropic account.

1. Go to **[console.anthropic.com](https://console.anthropic.com)** and create an account.
2. Go to **Billing** and add a small amount of credit (**$5 is plenty** to start).
3. Go to **API Keys** → **Create Key**. Name it `MathAssistant` and click **Create**.
4. **Copy** the key. It starts with `sk-ant-`. Keep it private, like a password.

### Step 4: Add the key to MathAssistant

1. The first time, MathAssistant opens on the **Settings** page.
2. Paste your key into **API key** and click **Test key**.
3. When it says **"Key works. You're ready to go."**, click **Tutor** at the top.

Your key is saved in your computer's own secure password store (**Windows Credential Manager** or the **Mac Keychain**), not in a file. It's only ever sent to Anthropic.

---

## Using MathAssistant

### Start a problem

On the **Tutor** page, pick one:

- **Math:** type the problem in the box. Click the **keyboard icon** in the box for a math keyboard with tabs for Basic, Algebra, Functions, Calculus, and Advanced math. Your computer keyboard works too.
- **Word problem:** switch to **Word problem** and type or paste it exactly as written.
- **📷 Camera:** take a picture with your computer's camera. The first time, your browser asks to use the camera; click **Allow**.
- **🖼 Photo, screenshot, or PDF:** choose a file, like a photo from your phone that you copied to the computer, or a worksheet PDF.
- **Paste a screenshot:** take a screenshot (**Windows:** `Win + Shift + S`, **Mac:** `Cmd + Ctrl + Shift + 4`), then press **Ctrl + V** (Mac: **Cmd + V**) on the Tutor page.

For pictures and PDFs:

1. **Drag a box** around the problem you want, or click **Read whole image**.
2. If the page has **several problems**, you'll see a list. Click the one to **start with**. The others are saved to **Up next** so you can do them later.
3. **Check** that the problem was read correctly, fix anything that's wrong, and click **Start**.

For a PDF, use **Prev / Next** to find the page, then **Use this page**, or **Read all pages** to list every problem in the document (up to 10 pages at a time).

### Work through it

- The tutor asks **one question at a time**. Answer in the box at the bottom:
  - **Math**: type a number or expression, for example `25` or `2x + 2`.
  - **Words**: explain your thinking, or ask a question like *"what does distribute mean?"*
- Different ways of writing the same answer are fine: `2(x+1)` and `2x+2` both count.
- If you're stuck, just say so. The tutor gives a smaller hint. It **won't give you the answer**. That's the point!
- The panel on the right shows your **steps** (✓ = done). Sometimes it shows a **similar example** to help.
- When you get a step right, the tutor moves on. If you had to try a few times, it asks one quick "why" question first to make sure it clicked.

### Stop and come back later

Problems save automatically. Click **My problems** to see:

- **Up next**: problems from a worksheet you haven't started yet.
- **In progress**: pick up exactly where you left off.
- **Completed**: problems you've solved.

### When you're done

Click **Quit** at the top of the page, or close the small **"MathAssistant is running"** window. (Closing only the browser tab leaves it running. Use **Open MathAssistant** in the small window to get back to it.)

---

## What does it cost?

MathAssistant itself is free. The AI costs a little each time the tutor thinks:

- A typical problem costs **about 1 to 5 cents** with the default model (Claude Haiku 4.5).
- Reading a photo or PDF page adds about a cent.
- **Settings → Usage** shows how much the current problem has used.
- You can set spending limits in your Anthropic account under **Billing**.

---

## Privacy

- Everything runs **on your computer**. Nothing is sent to us. There are no accounts, ads, or analytics.
- The only things that leave your computer:
  - your problem and your answers, sent to **Anthropic** so the AI can tutor you;
  - once when the app starts, a check with **GitHub** for a newer version. This sends nothing about you, and you can turn it off in **Settings → Updates**.
- Photos and PDFs are **not saved**. Only the problem text is kept.
- Your saved problems stay in a folder on your computer (see [Removing MathAssistant](#removing-mathassistant)).

---

## Updating

When a new version is out, MathAssistant shows **"A new version of MathAssistant is available"** at the top of the page.

1. Click **Download it** and get the file for your computer (same as [Step 1](#step-1-download)).
2. **Quit** MathAssistant.
3. **Windows:** extract the new zip and replace your old MathAssistant folder with the new one. **Mac:** drag the new MathAssistant into Applications and choose **Replace**.
4. Open it. You may see the first-time warning again (see [Step 2](#step-2-open-it-for-the-first-time)).

Your saved problems and your AI key are kept; they're stored separately from the app.

---

## Removing MathAssistant

1. Open MathAssistant → **Settings** → **Remove key** (this removes your key from the computer's password store).
2. Optional: **Settings → Delete all problems**.
3. Quit, then delete the **MathAssistant** folder (Windows) or drag **MathAssistant** from Applications to the Trash (Mac).
4. Optional: delete the saved-data folder:
   - **Windows:** `%LOCALAPPDATA%\mathassistant` (paste that into the File Explorer address bar)
   - **Mac:** `~/Library/Application Support/mathassistant` and `~/Library/Logs/mathassistant` (in Finder: **Go → Go to Folder…**)

---

## Troubleshooting

**The browser didn't open.** Click **Open MathAssistant** in the small "MathAssistant is running" window.

**Nothing happens when I open it again.** It's probably already running. Look for the small window (check the taskbar or Dock); opening it again just re-opens the browser tab.

**"The API key was rejected."** The key was mistyped, expired, or deleted. Create a new one ([Step 3](#step-3-get-an-ai-key)) and paste it into Settings.

**"Your AI provider account is out of credits."** Add credit at [console.anthropic.com](https://console.anthropic.com) → Billing.

**The camera doesn't work.** Click the camera icon (or the lock) in the browser's address bar and choose **Allow**. Close other apps that use the camera (like video calls). You can always use **Photo, screenshot, or PDF** instead.

**It misread my photo.** Fix the problem in the box before clicking Start. For better results: good light, hold the page flat, and drag a box around just one problem.

**Windows: antivirus or "Windows protected your PC" keeps blocking it.** Because the app isn't code-signed, some antivirus programs are cautious. Use **More info → Run anyway**, or allow MathAssistant in your antivirus settings.

**Mac: "MathAssistant is damaged and can't be opened."** This can happen with unsigned apps downloaded from the internet. Open **Terminal** and run this, then open the app again:

```
xattr -dr com.apple.quarantine /Applications/MathAssistant.app
```

**Something else went wrong.** Quit and reopen MathAssistant. Your problems are saved. If it keeps happening, the log file can help: `%LOCALAPPDATA%\mathassistant\Logs` (Windows) or `~/Library/Logs/mathassistant` (Mac). The log never contains your AI key.

---

## For developers

See **[docs/DEVELOPING.md](docs/DEVELOPING.md)** for running from source, tests, building the apps, and publishing releases. The design is in [docs/MATH_TUTOR_SPEC.md](docs/MATH_TUTOR_SPEC.md) and the code layout in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License

MIT. See [LICENSE](LICENSE).
