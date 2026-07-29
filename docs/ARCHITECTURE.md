# LingoLens Architecture

> **Architecture first. Features second.**

---

# Purpose

LingoLens is a desktop application that allows users to translate text from anywhere on the Windows desktop in real time.

Unlike traditional OCR applications that capture a screenshot and display translated text in a separate window, LingoLens is designed to behave like a **translation lens** that reveals translated content directly over the desktop.

The architecture is designed to be scalable, modular, and independent of the user interface.

---

# Vision

The goal is to create an application where a user can:

- Read any language PDFs
- Browse foreign language websites
- Read Microsoft Teams messages
- Watch subtitles
- Read software interfaces
- Work across multiple monitors

The translation should always correspond to whatever is currently visible beneath the Floating Lens.

The Floating Lens is simply the user's window into the translated desktop.

---

# Core Principles

## 1. Separate Responsibilities

Every major task has a single responsibility.

- Capture Engine captures pixels.
- OCR Engine extracts text.
- Translation Engine translates text.
- Translation Map stores translated information.
- Floating Lens displays translated information.

No component should perform another component's job.

---

## 2. UI Independence

The translation pipeline must work without any graphical user interface.

The user interface is a presentation layer built on top of the translation engine.

---

## 3. Platform Independence

Only the capture layer should know how images are obtained from Windows.

Everything above the capture layer should remain platform independent.

---

## 4. Coordinate Consistency

Every translation is referenced using desktop coordinates.

No component should invent its own coordinate system.

---

# High-Level Architecture

```
Windows Desktop
        │
        ▼
Capture Engine
        │
        ▼
OCR Engine
        │
        ▼
Translation Engine
        │
        ▼
Translation Map
        │
        ▼
Floating Lens
```

---

# Component Responsibilities

## Windows Desktop

Represents everything currently visible to the user.

Examples:

- PDF readers
- Web browsers
- Microsoft Teams
- PowerPoint
- Any desktop application

---

## Capture Engine

Responsibilities:

- Capture desktop images
- Handle multiple monitors
- Handle DPI scaling
- Provide images for OCR

Does NOT:

- Perform OCR
- Translate text
- Draw UI

---

## OCR Engine

Responsibilities:

- Detect text
- Extract characters
- Produce text locations

Example output:

Rectangle

```
x = 420
y = 185
width = 180
height = 32
```

Text

```
こんにちは世界
```

---

## Translation Engine

Responsibilities:

- Translate OCR output
- Preserve positional information
- Remain independent of UI

Example

Original

```
こんにちは世界
```

Translation

```
Hello World
```

Rectangle

```
420,185,180,32
```

---

## Translation Map

The Translation Map is the heart of LingoLens.

It stores:

- Original text
- Translated text
- Desktop coordinates

Example

```
Rectangle:
(420,185,180,32)

Original:
こんにちは世界

Translation:
Hello World
```

The Translation Map is completely independent from the user interface.

---

## Floating Lens

The Floating Lens is NOT responsible for:

- Capturing images
- OCR
- Translation

Instead, it asks:

> "What translated content exists beneath my current desktop position?"

It simply displays the appropriate section of the Translation Map.

The Floating Lens is a viewport.

---

# Event Flow

Desktop changes

↓

Capture Engine

↓

OCR Engine

↓

Translation Engine

↓

Translation Map Updated

↓

Floating Lens Refreshes

---

# Lens Movement

Moving the Floating Lens should NOT trigger:

- Screen capture
- OCR
- Translation

Moving the lens only changes which part of the Translation Map is displayed.

Translation should only occur when the desktop content changes.

Examples:

- User scrolls a PDF
- User changes browser page
- Teams message appears
- Video subtitle changes

---

# Coordinate Systems

LingoLens uses only two coordinate systems.

## 1. Desktop Coordinates

Used by:

- Capture Engine
- OCR Engine
- Translation Engine
- Translation Map

Everything references Windows desktop coordinates.

---

## 2. Lens Coordinates

Used only for rendering inside the Floating Lens.

The lens converts desktop coordinates into its own local drawing coordinates.

No additional coordinate systems should be introduced unless absolutely necessary.

---

# Multi-Monitor Support

The architecture must support:

- One monitor
- Multiple monitors
- Different resolutions
- Different DPI scaling

If the Floating Lens is positioned on Monitor 2, it must display translations that belong only to Monitor 2.

---

# Resolution Independence

The application must never assume a fixed resolution.

It should support:

- 1080p
- 1440p
- 4K
- Ultrawide
- Mixed monitor resolutions

Desktop coordinates should remain the single source of truth.

---

# Future Expansion

The architecture is designed so additional features can be added without redesigning the core.

Possible future components include:

- AI Context Translation
- OCR caching
- Translation caching
- Multiple OCR engines
- Multiple translation providers
- Plugin system
- Windows Magnification API
- GPU acceleration
- Offline translation models

---

# Architectural Rules

Every new feature should follow these rules:

1. One responsibility per component.
2. UI never performs OCR or translation.
3. Translation data belongs in the Translation Map.
4. Desktop coordinates are the single source of truth.
5. The Floating Lens is only a viewport.
6. Architecture is preferred over shortcuts.
7. Features must not compromise maintainability.

---

# Guiding Principle

> **LingoLens does not translate the Floating Lens. LingoLens translates the Windows desktop. The Floating Lens simply reveals the translated desktop beneath it.**