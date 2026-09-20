import { useCallback, useMemo, useState } from "react";
import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { Admin } from "./pages/Admin";
import { Alerts } from "./pages/Alerts";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";
import { Reports } from "./pages/Reports";
import { AuthContext, loadStoredToken, loginRequest, storeToken } from "./services/auth";

export function App() {
  const [sessionToken, setSessionToken] = useState<string | null>(loadStoredToken);

  const login = useCallback(async (email: string, password: string) => {
    const token = await loginRequest(email, password);
    storeToken(token);
    setSessionToken(token);
  }, []);

  const logout = useCallback(() => {
    storeToken(null);
    setSessionToken(null);
  }, []);

  const authValue = useMemo(() => ({ sessionToken, login, logout }), [sessionToken, login, logout]);

  return (
    <AuthContext.Provider value={authValue}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/alerts" element={<Alerts />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthContext.Provider>
  );
}
