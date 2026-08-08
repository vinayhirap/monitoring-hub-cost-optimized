export default function StatCard({ label, value, color }) {
  return (
    <div style={styles.card}>
      <div style={styles.label}>{label}</div>
      <div style={{ ...styles.value, color: color === "red" ? "#ef4444" : "#22c55e" }}>
        {value}
      </div>
    </div>
  );
}

const styles = {
  card: {
    background: "#020617",
    border: "1px solid #1e293b",
    borderRadius: "8px",
    padding: "16px",
  },
  label: { fontSize: "13px", color: "#94a3b8" },
  value: { fontSize: "28px", fontWeight: "600" },
};