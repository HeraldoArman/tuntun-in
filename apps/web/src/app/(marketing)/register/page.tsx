import { RegisterForm } from "@/modules/auth/register-form";

export default function RegisterPage() {
  return (
    <section className="flex min-h-screen bg-muted/30 px-4 py-16 md:py-32">
      <RegisterForm />
    </section>
  );
}
