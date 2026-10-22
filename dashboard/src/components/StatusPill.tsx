/** Status is a reserved palette and always ships with its label, never colour alone. */
export function StatusPill({ status }: { status: string }) {
  return <span className={`pill s-${status}`}>{status}</span>;
}
