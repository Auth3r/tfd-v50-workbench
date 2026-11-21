use gpw_offline_core::v50_handlers::{DispatchError, DomainHandler, Registry};
use gpw_offline_core::v50_schema::PROCEDURES;

type Register = fn(&mut Registry<u8>, DomainHandler<u8>) -> Result<(), DispatchError>;

fn verify_domain(register: Register, ids: &[u16]) {
    let mut registry = Registry::default();
    register(&mut registry, |state, schema, body| {
        // Deliberately synthetic. Both the schema and the original bytes cross the dispatch boundary.
        let [byte] = body else {
            return Err(DispatchError::InvalidBody);
        };
        Ok(Some(
            [schema.id.to_le_bytes().as_slice(), &[*state, *byte]].concat(),
        ))
    })
    .unwrap();

    let mut missing = 0;
    for &id in ids {
        match PROCEDURES.iter().find(|schema| schema.id == id) {
            Some(schema) => {
                missing += usize::from(schema.request.is_none() || schema.response.is_none());
                assert_eq!(
                    registry.dispatch(id, &7, b"V"),
                    Ok(Some([id.to_le_bytes().as_slice(), b"\x07V"].concat()))
                );
                assert_eq!(
                    registry.dispatch(id, &7, b""),
                    Err(DispatchError::InvalidBody)
                );
            }
            None => {
                missing += 1;
                assert_eq!(
                    registry.dispatch(id, &7, b"V"),
                    Err(DispatchError::UnknownProcedure)
                );
            }
        }
    }
    println!("V50_MISSING_DECLARATIONS={missing}");
}

#[test]
fn account_save() {
    verify_domain(Registry::register_account_save, &[2800]);
}

#[test]
fn quest() {
    verify_domain(Registry::register_quest, &[3600, 3601]);
}

#[test]
fn shop() {
    verify_domain(Registry::register_shop, &[409, 410, 601, 1603, 3201]);
}

#[test]
fn mail() {
    verify_domain(
        Registry::register_mail,
        &[
            1401, 1402, 1403, 1404, 1405, 1406, 1407, 1408, 1409, 1410, 1411, 1412, 1413, 1414,
            1415,
        ],
    );
}

#[test]
fn instance() {
    verify_domain(
        Registry::register_instance,
        &[1311, 1327, 1328, 3700, 11405],
    );
}

#[test]
fn live() {
    verify_domain(
        Registry::register_live,
        &[
            161, 1701, 1901, 2101, 2501, 2504, 2900, 3801, 3901, 3905, 3907, 3914, 3920, 4100,
        ],
    );
}
