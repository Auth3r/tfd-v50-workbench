use gpw_offline_core::session::{RequestState::*, Service::*, Session, SessionError::*};

fn session() -> Session {
    Session::new(0, 30_000, 100, 16).unwrap()
}

#[test]
fn identical_ids_in_different_services_complete_independently() {
    let mut s = session();
    s.begin(0, Login, 2, 1).unwrap();
    s.begin(1, Client, 2, 1003).unwrap();
    assert_eq!(s.response(2, Client, 2, 1003), Ok(Completed));
    assert_eq!(s.state(Login, 2), Some(AwaitingResponse));
    assert_eq!(s.response(3, Login, 2, 1), Ok(Completed));
}

#[test]
fn notifications_correlate_to_cause_not_latest_reservation() {
    let mut s = session();
    s.begin(0, Client, 12, 1110).unwrap();
    s.begin(1, Client, 13, 1110).unwrap();
    s.response(2, Client, 12, 1110).unwrap();
    s.response(3, Client, 13, 1110).unwrap();
    assert_eq!(s.notification(4, Client, 1120, 12), Ok(Completed));
    assert_eq!(s.state(Client, 13), Some(AwaitingNotification));
    assert_eq!(s.notification(5, Client, 1120, 13), Ok(Completed));
    assert_eq!(s.notification(6, Client, 1120, -1), Err(UnknownRequest));
    assert_eq!(s.notification(7, Client, 1120, 12), Err(DuplicateEvent));
}

#[test]
fn asynchronous_notification_does_not_stand_in_for_response() {
    let mut s = session();
    s.begin(0, Client, 12, 1110).unwrap();
    assert_eq!(
        s.notification(1, Client, 1120, 12),
        Ok(AwaitingReservationResponse)
    );
    assert_eq!(s.notification(2, Client, 1120, 12), Err(DuplicateEvent));
    assert_eq!(s.response(3, Client, 12, 1110), Ok(Completed));
    assert_eq!(s.response(4, Client, 12, 1110), Err(DuplicateEvent));
}

#[test]
fn mismatched_service_procedure_and_cause_leave_request_pending() {
    let mut s = session();
    s.begin(0, Client, 12, 1110).unwrap();
    s.begin(0, Client, 13, 1400).unwrap();
    assert_eq!(s.response(1, Game, 12, 1110), Err(UnknownRequest));
    assert_eq!(s.response(2, Client, 12, 1120), Err(ProcedureMismatch));
    assert_eq!(s.notification(3, Login, 1120, 12), Err(InvalidNotification));
    assert_eq!(s.notification(4, Client, 1120, 13), Err(ProcedureMismatch));
    assert_eq!(s.state(Client, 12), Some(AwaitingResponseAndNotification));
    assert_eq!(s.response(5, Client, 13, 1400), Ok(Completed));
}

#[test]
fn expired_requests_and_reused_ids_cannot_accept_late_events() {
    let mut s = session();
    s.begin(0, Client, 12, 1110).unwrap();
    assert_eq!(s.response(100, Client, 12, 1110), Err(LateEvent));
    assert_eq!(s.notification(101, Client, 1120, 12), Err(LateEvent));
    assert_eq!(s.state(Client, 12), Some(TimedOut));
    assert_eq!(s.begin(102, Client, 12, 1110), Err(IdAlreadyUsed));
}

#[test]
fn disconnect_and_idle_expiry_release_pending_work_and_new_session_is_clean() {
    for idle in [false, true] {
        let mut s = session();
        s.begin(0, Client, 12, 1110).unwrap();
        if idle {
            assert_eq!(s.advance(30_000), Err(Closed));
        } else {
            s.disconnect();
        }
        assert_eq!(s.state(Client, 12), Some(Cancelled));
        assert_eq!(s.response(30_001, Client, 12, 1110), Err(Closed));
        assert_eq!(s.begin(30_001, Client, 14, 1400), Err(Closed));
        let mut next = session();
        assert!(next.begin(0, Client, 12, 1110).is_ok());
        assert_eq!(next.notification(1, Client, 1120, 99), Err(UnknownRequest));
    }
}

#[test]
fn bounded_session_rejects_id_reuse_clock_reversal_and_invalid_policy() {
    assert!(Session::new(0, 0, 100, 2).is_err());
    let mut s = Session::new(0, 100, 10, 1).unwrap();
    assert_eq!(s.begin(0, Client, -1, 1110), Err(InvalidRequest));
    s.begin(2, Client, 1, 1003).unwrap();
    assert_eq!(s.response(1, Client, 1, 1003), Err(ClockReversed));
    s.response(3, Client, 1, 1003).unwrap();
    assert_eq!(s.begin(4, Client, 1, 1003), Err(IdAlreadyUsed));
    assert_eq!(s.begin(5, Client, 2, 1003), Err(RequestLimit));
}
