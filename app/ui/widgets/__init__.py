"""UI widgets package exports."""

from app.ui.widgets.automation_dialog import AutomationDialog, NewTriggerDialog
from app.ui.widgets.chat_view import ChatView
from app.ui.widgets.confirmation_dialog import ConfirmationDialog
from app.ui.widgets.diagnostics_drawer import DiagnosticsDrawer
from app.ui.widgets.input_bar import InputBar
from app.ui.widgets.knowledge_dialog import KnowledgeDialog
from app.ui.widgets.memory_dialog import MemoryDialog
from app.ui.widgets.message_bubble import MessageBubble
from app.ui.widgets.pixel_core import CoreState, PixelCoreState, PixelCoreWidget
from app.ui.widgets.settings_dialog import SettingsDialog
from app.ui.widgets.sidebar import ConversationSidebar
from app.ui.widgets.status_bar import SystemStatusBar
from app.ui.widgets.tasks_dialog import NewTaskDialog, TasksDialog
from app.ui.widgets.tool_activity import ToolActivityWidget

__all__ = [
    "AutomationDialog",
    "ChatView",
    "ConfirmationDialog",
    "ConversationSidebar",
    "CoreState",
    "DiagnosticsDrawer",
    "InputBar",
    "KnowledgeDialog",
    "MemoryDialog",
    "MessageBubble",
    "NewTaskDialog",
    "NewTriggerDialog",
    "PixelCoreState",
    "PixelCoreWidget",
    "SettingsDialog",
    "SystemStatusBar",
    "TasksDialog",
    "ToolActivityWidget",
]
