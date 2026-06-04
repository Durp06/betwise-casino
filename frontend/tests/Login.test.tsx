/**
 * Login.test.tsx — sign-up email-verification UX.
 *
 * When Supabase requires email confirmation, signUp returns no session. The
 * form must tell the user to verify their email (and flip to Sign In) — and must
 * NOT call the authed createMe, which would 401 and surface a misleading
 * "session expired" message.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Login from "../src/pages/Login";

const { signUpMock, signInMock, createMeMock } = vi.hoisted(() => ({
  signUpMock: vi.fn(),
  signInMock: vi.fn(),
  createMeMock: vi.fn(),
}));

vi.mock("../src/auth/supabase", () => ({
  supabase: { auth: { signUp: signUpMock, signInWithPassword: signInMock } },
  useSession: () => ({ session: null, loading: false }),
}));
vi.mock("../src/api/client", () => ({ createMe: createMeMock }));
// Chipy renders an animated mascot we don't need in this test.
vi.mock("../src/components/Chipy", () => ({ default: () => null }));

beforeEach(() => {
  signUpMock.mockReset();
  signInMock.mockReset();
  createMeMock.mockReset();
});

function fillSignUpForm(container: HTMLElement): void {
  // In sign-in mode the only "Sign Up" button is the mode toggle; click it.
  fireEvent.click(screen.getByRole("button", { name: "Sign Up" }));
  fireEvent.change(screen.getByPlaceholderText(/Username/i), { target: { value: "alice" } });
  fireEvent.change(screen.getByPlaceholderText("Email"), { target: { value: "alice@example.com" } });
  fireEvent.change(screen.getByPlaceholderText("Password"), { target: { value: "secret123" } });
  // Submit the form directly (avoids the two "Sign Up" buttons once in sign-up mode).
  fireEvent.submit(container.querySelector("form") as HTMLFormElement);
}

describe("Login — sign-up email verification", () => {
  it("prompts the user to verify their email and does NOT call createMe when no session is returned", async () => {
    signUpMock.mockResolvedValue({ data: { session: null, user: { id: "u1" } }, error: null });

    const { container } = render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );
    fillSignUpForm(container);

    await waitFor(() =>
      expect(screen.getByText(/check your email to verify/i)).toBeInTheDocument(),
    );
    // The authed profile-provision call must be skipped (no token yet)...
    expect(createMeMock).not.toHaveBeenCalled();
    // ...so the misleading "session expired" message never appears.
    expect(screen.queryByText(/session expired/i)).not.toBeInTheDocument();
  });

  it("provisions the profile immediately when signUp returns a session (confirmation disabled)", async () => {
    signUpMock.mockResolvedValue({ data: { session: { access_token: "t" }, user: { id: "u1" } }, error: null });
    createMeMock.mockResolvedValue({ data: { id: "u1" }, error: null });

    const { container } = render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );
    fillSignUpForm(container);

    await waitFor(() => expect(createMeMock).toHaveBeenCalledWith("alice"));
  });
});
