### 📊 Flow Diagram

```mermaid
flowchart TD
    A[User accesses /] --> B{Is user authenticated with Telegram?}
    
    B -- No --> C[Show phone login form]
    B -- Yes --> D[Fetch user info and dialogs]
    
    D --> E[Save groups/channels to DB if new]
    E --> F[Save user session to DB if not exists]
    F --> G[Fetch existing forwarding mappings]
    
    G --> H[Render select_groups.html with dialogs & selected mappings]

    H --> I[User selects source & target groups]
    I --> J[POST /start-forwarding]
    
    J --> K[Delete old mappings from DB]
    K --> L[Insert new mappings to DB]
    L --> M[Cache active mappings in memory]
    M --> N[Register event handler for new messages]

    N --> O[Redirect to status.html with active mapping summary]

    O --> P[User clicks Stop or Pause]

    P --> Q{Action Type}
    Q -- Stop --> R[Remove user’s mappings from memory]
    Q -- Pause --> S[Mark user’s mappings as paused (not implemented yet)]

    R --> T[Redirect to /]
    S --> T

    subgraph Debug Route
        U[GET /debug-mappings] --> V[Return user’s mapping as JSON]
    end
```

---

### 📝 Description of Flow
- **Authentication** via Telegram is required.
- Once authenticated, the system:
  - Pulls the user’s groups/channels.
  - Stores them in DB if not already there.
  - Loads forwarding mappings for pre-selection.
- User selects groups to forward **from → to**, submits the form.
- The system stores the mapping and registers a **Telethon event handler** to forward new messages.
- Users can also **pause or stop** forwarding.

