use gpw_offline_core::v50_save::SaveSnapshot;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() != 2 {
        return Err("usage: v50_save_map INPUT.tsv OUTPUT.tsv".into());
    }
    let snapshot = SaveSnapshot::from_exchange(&std::fs::read_to_string(&args[0])?)?;
    std::fs::write(&args[1], snapshot.to_exchange()?)?;
    println!(
        "Rust snapshot: accounts={} characters={} selections={} fields_per_character=10",
        snapshot.accounts.len(),
        snapshot.characters.len(),
        snapshot.selections.len()
    );
    Ok(())
}
