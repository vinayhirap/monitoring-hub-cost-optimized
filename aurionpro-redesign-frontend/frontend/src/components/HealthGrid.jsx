const services = [
  { name: "EC2", status: ["green", "green", "yellow", "red"] },
  { name: "RDS", status: ["green", "green", "green"] },
  { name: "EBS", status: ["green", "yellow"] },
  { name: "ALB", status: ["green", "green"] },
];

export default function HealthGrid() {
  return (
    <div>
      <h3 style={{ marginBottom: "12px" }}>Service Health</h3>
      <table style={styles.table}>
        <tbody>
          {services.map((svc) => (
            <tr key={svc.name}>
              <td style={styles.service}>{svc.name}</td>
              <td>
                {svc.status.map((s, i) => (
                  <span key={i} style={{ ...styles.dot, background: colorMap[s] }} />
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const colorMap = {
  green: "#22c55e",
  yellow: "#facc15",
  red: "#ef4444",
};

const styles = {
  table: {
    width: "100%",
    borderCollapse: "collapse",
  },
  service: {
    width: "80px",
    color: "#cbd5f5",
  },
  dot: {
    display: "inline-block",
    width: "14px",
    height: "14px",
    borderRadius: "50%",
    marginRight: "6px",
  },
};