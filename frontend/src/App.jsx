// monitoring-hub/frontend/src/App.jsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth }  from "./auth/AuthContext";
import Layout            from "./components/Layout";
import Login             from "./pages/Login";
import Overview          from "./pages/Overview";
import Alerts            from "./pages/Alerts";
import AccountDetail     from "./pages/AccountDetail";
import UserManagement    from "./pages/UserManagement";
import Compliance        from "./pages/Compliance";
import Settings          from "./pages/Settings";
import AccountOnboarding from "./pages/AccountOnboarding";
import ServiceList       from "./pages/ServiceList";
import ServiceDetail     from "./pages/ServiceDetail";

function RequireAuth({ children }) {
  const { isLoggedIn } = useAuth();
  return isLoggedIn ? children : <Navigate to="/login" replace />;
}

function AppRoutes() {
  const { isLoggedIn } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={isLoggedIn ? <Navigate to="/overview" replace /> : <Login />} />
      <Route path="/" element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Navigate to="/overview" replace />} />
        <Route path="overview"                  element={<Overview />} />
        <Route path="alerts"                    element={<Alerts />} />
        <Route path="onboarding"                element={<AccountOnboarding />} />
        <Route path="users"                     element={<UserManagement />} />
        <Route path="compliance"                element={<Compliance />} />
        <Route path="settings"                  element={<Settings />} />
        <Route path="accounts/:id/services"     element={<ServiceList />} />
        <Route path="accounts/:id/ec2"          element={<ServiceDetail service="EC2"    />} />
        <Route path="accounts/:id/ebs"          element={<ServiceDetail service="EBS"    />} />
        <Route path="accounts/:id/rds"          element={<ServiceDetail service="RDS"    />} />
        <Route path="accounts/:id/s3"           element={<ServiceDetail service="S3"     />} />
        <Route path="accounts/:id/ecs"          element={<ServiceDetail service="ECS"    />} />
        <Route path="accounts/:id/elb"          element={<ServiceDetail service="ELB"    />} />
        <Route path="accounts/:id/lambda"       element={<ServiceDetail service="Lambda" />} />
        <Route path="accounts/:id"              element={<AccountDetail />} />
      </Route>
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}