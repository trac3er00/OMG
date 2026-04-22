import React, { useState } from "react";

interface DataRow {
  id: number;
  name: string;
  email: string;
  role: string;
  status: "active" | "inactive";
}

const initialData: DataRow[] = [
  {
    id: 1,
    name: "Alice Johnson",
    email: "alice@example.com",
    role: "Admin",
    status: "active",
  },
  {
    id: 2,
    name: "Bob Smith",
    email: "bob@example.com",
    role: "User",
    status: "active",
  },
  {
    id: 3,
    name: "Carol White",
    email: "carol@example.com",
    role: "Editor",
    status: "inactive",
  },
  {
    id: 4,
    name: "David Brown",
    email: "david@example.com",
    role: "User",
    status: "active",
  },
  {
    id: 5,
    name: "Eve Davis",
    email: "eve@example.com",
    role: "Admin",
    status: "active",
  },
];

const App: React.FC = () => {
  const [data, setData] = useState<DataRow[]>(initialData);
  const [filter, setFilter] = useState("");
  const [sortField, setSortField] = useState<keyof DataRow>("name");
  const [sortAsc, setSortAsc] = useState(true);

  const filteredData = data
    .filter(
      (row) =>
        row.name.toLowerCase().includes(filter.toLowerCase()) ||
        row.email.toLowerCase().includes(filter.toLowerCase()) ||
        row.role.toLowerCase().includes(filter.toLowerCase()),
    )
    .sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      if (aVal < bVal) return sortAsc ? -1 : 1;
      if (aVal > bVal) return sortAsc ? 1 : -1;
      return 0;
    });

  const handleSort = (field: keyof DataRow) => {
    if (field === sortField) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  const toggleStatus = (id: number) => {
    setData(
      data.map((row) =>
        row.id === id
          ? { ...row, status: row.status === "active" ? "inactive" : "active" }
          : row,
      ),
    );
  };

  const styles = {
    container: {
      fontFamily: "system-ui, sans-serif",
      padding: "2rem",
      maxWidth: "1200px",
      margin: "0 auto",
    },
    header: { marginBottom: "2rem" },
    title: { fontSize: "1.5rem", fontWeight: "bold", marginBottom: "0.5rem" },
    subtitle: { color: "#666" },
    searchInput: {
      padding: "0.5rem 1rem",
      fontSize: "1rem",
      border: "1px solid #ddd",
      borderRadius: "4px",
      width: "300px",
      marginBottom: "1rem",
    },
    table: {
      width: "100%",
      borderCollapse: "collapse" as const,
      boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
    },
    th: {
      padding: "0.75rem 1rem",
      textAlign: "left" as const,
      backgroundColor: "#f5f5f5",
      borderBottom: "2px solid #ddd",
      cursor: "pointer",
    },
    td: { padding: "0.75rem 1rem", borderBottom: "1px solid #eee" },
    statusActive: {
      padding: "0.25rem 0.5rem",
      borderRadius: "4px",
      fontSize: "0.875rem",
      backgroundColor: "#dcfce7",
      color: "#166534",
    },
    statusInactive: {
      padding: "0.25rem 0.5rem",
      borderRadius: "4px",
      fontSize: "0.875rem",
      backgroundColor: "#fee2e2",
      color: "#991b1b",
    },
    button: {
      padding: "0.25rem 0.5rem",
      border: "1px solid #ddd",
      borderRadius: "4px",
      cursor: "pointer",
      backgroundColor: "#fff",
    },
    stats: { display: "flex", gap: "2rem", marginBottom: "1rem" },
    stat: { padding: "1rem", backgroundColor: "#f8f9fa", borderRadius: "8px" },
  };

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h1 style={styles.title}>{{ project_name }} Admin Dashboard</h1>
        <p style={styles.subtitle}>Manage users and system settings</p>
      </header>

      <div style={styles.stats}>
        <div style={styles.stat}>
          <strong>{data.length}</strong> Total Users
        </div>
        <div style={styles.stat}>
          <strong>{data.filter((d) => d.status === "active").length}</strong>{" "}
          Active
        </div>
        <div style={styles.stat}>
          <strong>{data.filter((d) => d.status === "inactive").length}</strong>{" "}
          Inactive
        </div>
      </div>

      <input
        type="text"
        placeholder="Search users..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={styles.searchInput}
      />

      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th} onClick={() => handleSort("name")}>
              Name {sortField === "name" && (sortAsc ? "↑" : "↓")}
            </th>
            <th style={styles.th} onClick={() => handleSort("email")}>
              Email {sortField === "email" && (sortAsc ? "↑" : "↓")}
            </th>
            <th style={styles.th} onClick={() => handleSort("role")}>
              Role {sortField === "role" && (sortAsc ? "↑" : "↓")}
            </th>
            <th style={styles.th}>Status</th>
            <th style={styles.th}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {filteredData.map((row) => (
            <tr key={row.id}>
              <td style={styles.td}>{row.name}</td>
              <td style={styles.td}>{row.email}</td>
              <td style={styles.td}>{row.role}</td>
              <td style={styles.td}>
                <span
                  style={
                    row.status === "active"
                      ? styles.statusActive
                      : styles.statusInactive
                  }
                >
                  {row.status}
                </span>
              </td>
              <td style={styles.td}>
                <button
                  style={styles.button}
                  onClick={() => toggleStatus(row.id)}
                >
                  Toggle Status
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default App;
