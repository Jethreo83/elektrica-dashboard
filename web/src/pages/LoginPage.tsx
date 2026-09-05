// LoginPage.tsx — dev convenience screen. The real sign-in path is
// via the shell dashboard's Launcher (http://localhost:5173), which
// opens this app with ?token=<jwt> after Google login. This screen
// exists so this dashboard is still directly clickable/demoable even
// when the shell isn't running -- paste a token issued by the shell
// (or minted by scripts/mint_dev_token.py for local testing).
import { useState } from 'react';
import { useAuth } from '../auth';

export default function LoginPage() {
  const { setToken, error } = useAuth();
  const [value, setValue] = useState('');

  return (
    <div className="ek-login">
      <div className="ek-login-card">
        <div className="ek-login-logo">Elektrica Rentals</div>
        <p className="ek-login-sub">Staff Dashboard</p>
        <p style={{ fontSize: 13, color: 'var(--ek-gray)', marginBottom: 16 }}>
          Sign in via the Elektrica launcher (shell dashboard), which will
          redirect here with your session. For local dev without the
          shell running, paste a signed session token below.
        </p>
        {error && <p style={{ color: 'var(--ek-danger)', fontSize: 13 }}>{error}</p>}
        <textarea
          className="ek-input"
          placeholder="Paste session token…"
          rows={4}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          style={{ width: '100%', marginBottom: 12, resize: 'vertical' }}
        />
        <button className="ek-btn" onClick={() => value.trim() && setToken(value.trim())} disabled={!value.trim()}>
          Continue
        </button>
      </div>
    </div>
  );
}
