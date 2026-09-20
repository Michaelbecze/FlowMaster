import { Navigate } from "react-router-dom";
import { useAuth } from "../services/auth";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  if (!auth.sessionToken) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
