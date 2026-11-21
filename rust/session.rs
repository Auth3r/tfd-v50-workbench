//! Service-scoped request lifecycle, independent of the UNKNOWN V15 body codec.
//! 1110 -> 1120 uses cause_request_id. This never allocates a world or Oid.
use std::collections::BTreeMap;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Service {
    Login,
    Client,
    Game,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RequestState {
    AwaitingResponse,
    AwaitingResponseAndNotification,
    AwaitingNotification,
    AwaitingReservationResponse,
    Completed,
    TimedOut,
    Cancelled,
}

impl RequestState {
    fn terminal(self) -> bool {
        matches!(self, Self::Completed | Self::TimedOut | Self::Cancelled)
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum SessionError {
    Closed,
    ClockReversed,
    InvalidPolicy,
    InvalidRequest,
    IdAlreadyUsed,
    RequestLimit,
    UnknownRequest,
    ProcedureMismatch,
    DuplicateEvent,
    LateEvent,
    InvalidNotification,
}

#[derive(Default, Debug, PartialEq, Eq)]
pub struct RequestCounts {
    pub pending: usize,
    pub completed: usize,
    pub timed_out: usize,
    pub cancelled: usize,
}

struct Request {
    procedure: u16,
    deadline: u64,
    state: RequestState,
}

/// One GPW local connection/session. IDs are never reused within this session,
/// including terminal requests, so delayed notifications cannot bind to new work.
pub struct Session {
    requests: BTreeMap<(Service, i32), Request>,
    last_tick: u64,
    idle_deadline: u64,
    idle_ms: u64,
    request_ms: u64,
    limit: usize,
    closed: bool,
}

impl Session {
    /// Timeouts and limits are GPW policy, not recovered V15 constants.
    pub fn new(
        now: u64,
        idle_ms: u64,
        request_ms: u64,
        limit: usize,
    ) -> Result<Self, SessionError> {
        if idle_ms == 0 || request_ms == 0 || !(1..=4096).contains(&limit) {
            return Err(SessionError::InvalidPolicy);
        }
        Ok(Self {
            requests: BTreeMap::new(),
            last_tick: now,
            idle_deadline: now.saturating_add(idle_ms),
            idle_ms,
            request_ms,
            limit,
            closed: false,
        })
    }

    pub fn advance(&mut self, now: u64) -> Result<(), SessionError> {
        if now < self.last_tick {
            return Err(SessionError::ClockReversed);
        }
        self.last_tick = now;
        if !self.closed && now >= self.idle_deadline {
            self.disconnect();
        }
        for request in self.requests.values_mut() {
            if !request.state.terminal() && now >= request.deadline {
                request.state = RequestState::TimedOut;
            }
        }
        if self.closed {
            return Err(SessionError::Closed);
        }
        Ok(())
    }

    fn touch(&mut self, now: u64) {
        self.idle_deadline = now.saturating_add(self.idle_ms);
    }

    pub fn begin(
        &mut self,
        now: u64,
        service: Service,
        id: i32,
        procedure: u16,
    ) -> Result<RequestState, SessionError> {
        self.advance(now)?;
        if id < 0 || procedure > 32767 || procedure == 1120 {
            return Err(SessionError::InvalidRequest);
        }
        if self.requests.contains_key(&(service, id)) {
            return Err(SessionError::IdAlreadyUsed);
        }
        if self.requests.len() >= self.limit {
            return Err(SessionError::RequestLimit);
        }
        let state = if service == Service::Client && procedure == 1110 {
            RequestState::AwaitingResponseAndNotification
        } else {
            RequestState::AwaitingResponse
        };
        self.requests.insert(
            (service, id),
            Request {
                procedure,
                deadline: now.saturating_add(self.request_ms),
                state,
            },
        );
        self.touch(now);
        Ok(state)
    }

    pub fn response(
        &mut self,
        now: u64,
        service: Service,
        id: i32,
        procedure: u16,
    ) -> Result<RequestState, SessionError> {
        self.advance(now)?;
        let request = self
            .requests
            .get_mut(&(service, id))
            .ok_or(SessionError::UnknownRequest)?;
        if procedure != request.procedure {
            return Err(SessionError::ProcedureMismatch);
        }
        request.state = match request.state {
            RequestState::AwaitingResponse => RequestState::Completed,
            RequestState::AwaitingResponseAndNotification => RequestState::AwaitingNotification,
            RequestState::AwaitingReservationResponse => RequestState::Completed,
            RequestState::Completed | RequestState::AwaitingNotification => {
                return Err(SessionError::DuplicateEvent);
            }
            RequestState::TimedOut | RequestState::Cancelled => {
                return Err(SessionError::LateEvent);
            }
        };
        let state = request.state;
        self.touch(now);
        Ok(state)
    }

    /// The notification's own request_id is deliberately not used as a key.
    /// A completed correlation means metadata was associated, never world success.
    pub fn notification(
        &mut self,
        now: u64,
        service: Service,
        procedure: u16,
        cause_request_id: i32,
    ) -> Result<RequestState, SessionError> {
        self.advance(now)?;
        if service != Service::Client || procedure != 1120 {
            return Err(SessionError::InvalidNotification);
        }
        let request = self
            .requests
            .get_mut(&(service, cause_request_id))
            .ok_or(SessionError::UnknownRequest)?;
        if request.procedure != 1110 {
            return Err(SessionError::ProcedureMismatch);
        }
        request.state = match request.state {
            RequestState::AwaitingResponseAndNotification => {
                RequestState::AwaitingReservationResponse
            }
            RequestState::AwaitingNotification => RequestState::Completed,
            RequestState::Completed | RequestState::AwaitingReservationResponse => {
                return Err(SessionError::DuplicateEvent);
            }
            RequestState::TimedOut | RequestState::Cancelled => {
                return Err(SessionError::LateEvent);
            }
            RequestState::AwaitingResponse => return Err(SessionError::ProcedureMismatch),
        };
        let state = request.state;
        self.touch(now);
        Ok(state)
    }

    pub fn state(&self, service: Service, id: i32) -> Option<RequestState> {
        self.requests.get(&(service, id)).map(|r| r.state)
    }

    pub fn disconnect(&mut self) {
        self.closed = true;
        for request in self.requests.values_mut() {
            if !request.state.terminal() {
                request.state = RequestState::Cancelled;
            }
        }
    }

    pub fn counts(&self) -> RequestCounts {
        let mut counts = RequestCounts::default();
        for request in self.requests.values() {
            match request.state {
                RequestState::Completed => counts.completed += 1,
                RequestState::TimedOut => counts.timed_out += 1,
                RequestState::Cancelled => counts.cancelled += 1,
                _ => counts.pending += 1,
            }
        }
        counts
    }
}
