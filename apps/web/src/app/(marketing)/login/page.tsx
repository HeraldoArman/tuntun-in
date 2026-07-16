import { LoginForm } from "@/modules/auth/login-form";

export default function LoginPage() {
  return (
    <section className="flex min-h-screen bg-muted/30 px-4 py-16 md:py-32">
      <LoginForm />
    </section>
  );
}
