//! Byte-oriented dispatch invoked for an already parsed request.
use std::collections::BTreeMap;

use crate::v50_schema::{PROCEDURES, ProcedureSchema};

pub type Handler<S> = fn(&S, &[u8]) -> Option<Vec<u8>>;
pub type DomainHandler<S> = fn(&S, &ProcedureSchema, &[u8]) -> DispatchResult;
pub type DispatchResult = Result<Option<Vec<u8>>, DispatchError>;

enum Registered<S> {
    Handler(Handler<S>),
    Domain(&'static ProcedureSchema, DomainHandler<S>),
}

const QUEST_IDS: [u16; 2] = [3600, 3601];
const MAIL_IDS: [u16; 9] = [1401, 1402, 1403, 1404, 1405, 1406, 1410, 1414, 1415];

fn procedure_schema(id: u16) -> Result<&'static ProcedureSchema, DispatchError> {
    PROCEDURES
        .binary_search_by_key(&id, |schema| schema.id)
        .map(|index| &PROCEDURES[index])
        .map_err(|_| DispatchError::UnknownProcedure)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DispatchError {
    UnknownProcedure,
    Unimplemented,
    AlreadyRegistered,
    InvalidBody,
}

pub struct Registry<S> {
    handlers: BTreeMap<u16, Registered<S>>,
}

impl<S> Default for Registry<S> {
    fn default() -> Self {
        Self {
            handlers: BTreeMap::new(),
        }
    }
}

impl<S> Registry<S> {
    pub fn register(&mut self, id: u16, handler: Handler<S>) -> Result<(), DispatchError> {
        use std::collections::btree_map::Entry;

        procedure_schema(id)?;
        match self.handlers.entry(id) {
            Entry::Vacant(entry) => {
                entry.insert(Registered::Handler(handler));
                Ok(())
            }
            Entry::Occupied(_) => Err(DispatchError::AlreadyRegistered),
        }
    }

    /// Bind a self-owned quest codec/service to the two declared schemas.
    pub fn register_quest(&mut self, handler: DomainHandler<S>) -> Result<(), DispatchError> {
        self.register_domain(&QUEST_IDS, handler)
    }

    /// Bind a self-owned mail codec/service to the declared mail procedures.
    pub fn register_mail(&mut self, handler: DomainHandler<S>) -> Result<(), DispatchError> {
        self.register_domain(&MAIL_IDS, handler)
    }

    pub fn register_account_save(
        &mut self,
        handler: DomainHandler<S>,
    ) -> Result<(), DispatchError> {
        self.register_domain(&[2800], handler)
    }

    pub fn register_shop(&mut self, handler: DomainHandler<S>) -> Result<(), DispatchError> {
        self.register_domain(&[409, 410, 601, 1603, 3201], handler)
    }

    pub fn register_instance(&mut self, handler: DomainHandler<S>) -> Result<(), DispatchError> {
        self.register_domain(&[1311, 1327, 1328, 3700, 11405], handler)
    }

    pub fn register_live(&mut self, handler: DomainHandler<S>) -> Result<(), DispatchError> {
        self.register_domain(
            &[
                161, 1701, 1901, 2101, 2501, 2504, 2900, 3801, 3901, 3905, 3907, 3914, 3920, 4100,
            ],
            handler,
        )
    }

    fn register_domain(
        &mut self,
        ids: &[u16],
        handler: DomainHandler<S>,
    ) -> Result<(), DispatchError> {
        let schemas = ids
            .iter()
            .map(|&id| procedure_schema(id))
            .collect::<Result<Vec<_>, _>>()?;
        if ids.iter().any(|id| self.handlers.contains_key(id)) {
            return Err(DispatchError::AlreadyRegistered);
        }
        self.handlers.extend(
            schemas
                .into_iter()
                .map(|schema| (schema.id, Registered::Domain(schema, handler))),
        );
        Ok(())
    }

    /// Ok(None) means a registered handler intentionally returns no reply.
    pub fn dispatch(&self, id: u16, state: &S, request: &[u8]) -> DispatchResult {
        procedure_schema(id)?;
        match self.handlers.get(&id).ok_or(DispatchError::Unimplemented)? {
            Registered::Handler(handler) => Ok(handler(state, request)),
            Registered::Domain(schema, handler) => handler(state, schema, request),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dispatch_distinguishes_missing_handlers_and_intentional_no_reply() {
        let mut registry = Registry::<u8>::default();
        assert_eq!(
            registry.dispatch(0, &5, b"x"),
            Err(DispatchError::UnknownProcedure)
        );
        assert_eq!(
            registry.dispatch(409, &5, b"x"),
            Err(DispatchError::Unimplemented)
        );

        registry
            .register(409, |state, bytes| Some(vec![*state, bytes[0]]))
            .unwrap();
        assert_eq!(
            registry.register(409, |_, _| None),
            Err(DispatchError::AlreadyRegistered)
        );
        registry.register(1410, |_, _| None).unwrap();

        assert_eq!(registry.dispatch(409, &5, b"x"), Ok(Some(vec![5, b'x'])));
        assert_eq!(registry.dispatch(1410, &5, b"x"), Ok(None));
    }
}

#[cfg(test)]
mod quest {
    use super::*;

    #[test]
    fn dispatches_quest_bytes_and_preserves_missing_request_schema() {
        let mut registry = Registry::<u8>::default();
        registry
            .register_quest(|state, schema, bytes| match schema.id {
                3600 => {
                    assert_eq!(schema.request, Some("M1Request_GetCurrentWorldQuestInfos"));
                    assert_eq!(
                        schema.response,
                        Some("M1Response_GetCurrentWorldQuestInfos")
                    );
                    let [selector] = bytes else {
                        return Err(DispatchError::InvalidBody);
                    };
                    Ok(Some(vec![*state, *selector]))
                }
                3601 => {
                    assert_eq!(schema.request, None);
                    assert_eq!(schema.response, Some("M1Response_GetCurrentWorldBuffInfos"));
                    Err(DispatchError::Unimplemented)
                }
                _ => unreachable!(),
            })
            .unwrap();

        // Synthetic adapter contract only. The bytes have no V50 wire semantics.
        assert_eq!(registry.dispatch(3600, &5, b"x"), Ok(Some(vec![5, b'x'])));
        assert_eq!(
            registry.dispatch(3600, &5, b""),
            Err(DispatchError::InvalidBody)
        );
        assert_eq!(
            registry.dispatch(3601, &5, b""),
            Err(DispatchError::Unimplemented)
        );
    }
}

#[cfg(test)]
mod mail {
    use super::*;

    #[test]
    fn dispatches_declared_mail_ids_and_keeps_schema_holes_explicit() {
        let mut registry = Registry::<u8>::default();
        registry
            .register_mail(|state, schema, bytes| {
                assert!(schema.request.is_some());
                if schema.id == 1410 {
                    assert_eq!(schema.response, None);
                    return Err(DispatchError::Unimplemented);
                }
                assert!(schema.response.is_some());
                Ok(Some([&[*state], bytes].concat()))
            })
            .unwrap();

        for id in [1401, 1402, 1403, 1404, 1405, 1406, 1414, 1415] {
            assert_eq!(
                registry.dispatch(id, &5, b"mail"),
                Ok(Some(b"\x05mail".to_vec()))
            );
        }
        assert_eq!(
            registry.dispatch(1410, &5, b""),
            Err(DispatchError::Unimplemented)
        );
        for id in [1407, 1408, 1409, 1411, 1412, 1413] {
            assert_eq!(
                registry.dispatch(id, &5, b""),
                Err(DispatchError::UnknownProcedure)
            );
        }
    }

    #[test]
    fn conflicting_registration_leaves_entire_mail_domain_untouched() {
        let mut registry = Registry::<()>::default();
        registry.register(1415, |_, _| None).unwrap();
        assert_eq!(
            registry.register_mail(|_, _, _| unreachable!()),
            Err(DispatchError::AlreadyRegistered)
        );
        assert_eq!(
            registry.dispatch(1401, &(), b""),
            Err(DispatchError::Unimplemented)
        );
        assert_eq!(registry.dispatch(1415, &(), b""), Ok(None));
    }
}
