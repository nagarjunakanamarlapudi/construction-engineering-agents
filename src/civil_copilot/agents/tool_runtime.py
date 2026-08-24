"""Run-scoped identity and dependencies injected through LangChain ToolRuntime."""

from __future__ import annotations

import signal
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from queue import Empty, Queue
from time import monotonic
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol

from civil_copilot.calculation.service import CalculationService
from civil_copilot.schedule.service import ScheduleImpactService

if TYPE_CHECKING:
    from civil_copilot.agents.tools import ProjectTools


class ToolDeadlineExceeded(TimeoutError):
    """A native dependency deadline cancelled an operation before returning control."""


class ToolDeadlineUnavailable(RuntimeError):
    """No execution mechanism can enforce the requested deadline in this context."""


@dataclass(frozen=True)
class NativeDeadlineComponent:
    """One bounded dependency or deterministic step in a registered tool path."""

    name: str
    worst_case_seconds: float
    mechanism: Literal["native_timeout", "deterministic_bound"]

    def __post_init__(self) -> None:
        if not self.name.strip() or self.worst_case_seconds <= 0:
            raise ValueError("deadline components require a name and positive bound")


@dataclass(frozen=True, slots=True)
class NativeDeadlineProof:
    """Cumulative upper bound for one concrete registered tool operation."""

    tool_name: str
    worst_case_seconds: float
    components: tuple[NativeDeadlineComponent, ...]
    _issuer_identity: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not self.tool_name.strip() or not self.components:
            raise ValueError("native deadline proof requires a tool and components")
        cumulative = sum(component.worst_case_seconds for component in self.components)
        if abs(cumulative - self.worst_case_seconds) > 1e-9:
            raise ValueError("proof worst_case_seconds must equal its cumulative components")

    def _issued_for(self, issuer_identity: object) -> NativeDeadlineProof:
        issued = NativeDeadlineProof(
            tool_name=self.tool_name,
            worst_case_seconds=self.worst_case_seconds,
            components=self.components,
        )
        object.__setattr__(issued, "_issuer_identity", issuer_identity)
        return issued

    def _was_issued_by(self, issuer_identity: object) -> bool:
        return self._issuer_identity is issuer_identity


@dataclass(frozen=True, slots=True)
class VerifiedToolOperation:
    """Callable paired with the service-owned native deadline proof for its tool path."""

    operation: Callable[[], Any]
    proof: NativeDeadlineProof
    _issuer_identity: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    @classmethod
    def _issued_for(
        cls,
        *,
        operation: Callable[[], Any],
        proof: NativeDeadlineProof,
        issuer_identity: object,
    ) -> VerifiedToolOperation:
        issued = cls(operation=operation, proof=proof)
        object.__setattr__(issued, "_issuer_identity", issuer_identity)
        return issued

    def _was_issued_by(self, issuer_identity: object) -> bool:
        return self._issuer_identity is issuer_identity

    def __call__(self) -> Any:
        return self.operation()


ToolOperation = Callable[[], Any] | VerifiedToolOperation


class _SignalDeadlineExpired(BaseException):
    """Internal signal that user operations cannot accidentally catch as Exception."""


def _raise_signal_deadline(_signum: int, _frame: Any) -> None:
    raise _SignalDeadlineExpired


class ToolDeadlineRunner(Protocol):
    """Execute without copying live clients and cancel before returning on expiry."""

    enforces_deadline: Literal[True]

    def run(
        self,
        operation: ToolOperation,
        *,
        tool_name: str,
        timeout_seconds: float,
    ) -> Any: ...


@dataclass
class _DispatchedDeadlineCall:
    operation: ToolOperation
    tool_name: str
    timeout_seconds: float
    completed: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: BaseException | None = None


class MainThreadDeadlineDispatcher:
    """Marshal tool work to the process main thread for SIGALRM interruption."""

    def __init__(self) -> None:
        self._requests: Queue[_DispatchedDeadlineCall] = Queue()
        self._closed = threading.Event()

    def runner(self) -> SignalToolDeadlineRunner:
        return SignalToolDeadlineRunner(self)

    def submit(
        self,
        operation: ToolOperation,
        *,
        tool_name: str,
        timeout_seconds: float,
    ) -> Any:
        if self._closed.is_set():
            raise ToolDeadlineUnavailable("the main-thread deadline dispatcher is closed")
        call = _DispatchedDeadlineCall(operation, tool_name, timeout_seconds)
        self._requests.put(call)
        call.completed.wait()
        if call.error is not None:
            raise call.error
        return call.result

    def service_one(self, wait_seconds: float = 0.01) -> bool:
        if threading.current_thread() is not threading.main_thread():
            raise ToolDeadlineUnavailable("deadline dispatch must run on the process main thread")
        try:
            call = self._requests.get(timeout=wait_seconds)
        except Empty:
            return False
        try:
            call.result = SignalToolDeadlineRunner().run(
                call.operation,
                tool_name=call.tool_name,
                timeout_seconds=call.timeout_seconds,
            )
        except BaseException as error:
            call.error = error
        finally:
            call.completed.set()
        return True

    def close(self) -> None:
        self._closed.set()
        while True:
            try:
                call = self._requests.get_nowait()
            except Empty:
                break
            call.error = ToolDeadlineUnavailable(
                "the main-thread deadline dispatcher closed before execution"
            )
            call.completed.set()


class SignalToolDeadlineRunner:
    """Interrupt synchronous work with a process-main-thread POSIX timer."""

    enforces_deadline: ClassVar[Literal[True]] = True

    def __init__(self, dispatcher: MainThreadDeadlineDispatcher | None = None) -> None:
        self._dispatcher = dispatcher

    def run(
        self,
        operation: ToolOperation,
        *,
        tool_name: str,
        timeout_seconds: float,
    ) -> Any:
        supported_here = (
            timeout_seconds > 0
            and threading.current_thread() is threading.main_thread()
            and hasattr(signal, "SIGALRM")
            and hasattr(signal, "setitimer")
        )
        if not supported_here and self._dispatcher is not None:
            return self._dispatcher.submit(
                operation,
                tool_name=tool_name,
                timeout_seconds=timeout_seconds,
            )
        if not supported_here:
            raise ToolDeadlineUnavailable(
                f"no interruptible synchronous deadline is available for {tool_name}"
            )
        started = monotonic()
        previous_handler = signal.getsignal(signal.SIGALRM)
        previous_timer = signal.getitimer(signal.ITIMER_REAL)
        signal.signal(signal.SIGALRM, _raise_signal_deadline)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        try:
            return operation()
        except _SignalDeadlineExpired:
            raise ToolDeadlineExceeded(
                f"{tool_name} exceeded its native execution deadline"
            ) from None
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
            if previous_timer[0] > 0:
                signal.setitimer(
                    signal.ITIMER_REAL,
                    max(previous_timer[0] - (monotonic() - started), 1e-6),
                    previous_timer[1],
                )


@dataclass(frozen=True)
class AgentToolContext:
    user_id: str
    project_id: str
    access_scopes: tuple[str, ...]
    project_tools: ProjectTools
    schedule_service: ScheduleImpactService
    calculation_service: CalculationService
    request_id: str
    conversation_id: str | None = None
    max_steps: int | None = None
    max_model_calls: int | None = None
    deadline_monotonic: float | None = field(default=None, repr=False)
    prior_estimated_cost_usd: float = field(default=0.0, repr=False)
    request_max_cost_usd: float | None = field(default=None, repr=False)
    tool_deadline_runner: ToolDeadlineRunner | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    started_at_monotonic: float = field(default_factory=monotonic, repr=False)

    def __post_init__(self) -> None:
        for field_name in ("user_id", "project_id", "request_id"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.conversation_id is None:
            object.__setattr__(self, "conversation_id", f"conversation-{self.request_id}")
        elif not self.conversation_id.strip():
            raise ValueError("conversation_id must be non-empty")
        if self.max_steps is not None and self.max_steps < 1:
            raise ValueError("max_steps must be positive")
        if self.max_model_calls is not None and self.max_model_calls < 1:
            raise ValueError("max_model_calls must be positive")
        if self.deadline_monotonic is not None and self.deadline_monotonic <= 0:
            raise ValueError("deadline_monotonic must be positive")
        if self.prior_estimated_cost_usd < 0:
            raise ValueError("prior_estimated_cost_usd cannot be negative")
        if self.request_max_cost_usd is not None and self.request_max_cost_usd <= 0:
            raise ValueError("request_max_cost_usd must be positive")
