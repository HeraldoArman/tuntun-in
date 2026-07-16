"use client";

import { useForm } from "@tanstack/react-form";
import { Button } from "@tuntun-in/ui/components/button";
import { Input } from "@tuntun-in/ui/components/input";
import { Label } from "@tuntun-in/ui/components/label";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import z from "zod";
import { authClient } from "@/lib/auth-client";
import { GoogleSignInButton } from "./social-auth";

export function RegisterForm() {
  const router = useRouter();

  const form = useForm({
    defaultValues: {
      name: "",
      email: "",
      password: "",
    },
    onSubmit: async ({ value }) => {
      await authClient.signUp.email(
        {
          email: value.email,
          password: value.password,
          name: value.name,
        },
        {
          onSuccess: () => {
            router.push("/dashboard");
            toast.success("Sign up successful");
          },
          onError: (error) => {
            toast.error(error.error.message || error.error.statusText);
          },
        }
      );
    },
    validators: {
      onSubmit: z.object({
        name: z.string().min(2, "Name must be at least 2 characters"),
        email: z.email("Invalid email address"),
        password: z.string().min(8, "Password must be at least 8 characters"),
      }),
    },
  });

  return (
    <form
      className="m-auto h-fit w-full max-w-sm rounded-[calc(var(--radius)+.125rem)] border bg-card p-0.5 shadow-md"
      onSubmit={(e) => {
        e.preventDefault();
        e.stopPropagation();
        form.handleSubmit();
      }}
    >
      <div className="p-8 pb-6">
        <div>
          <Link aria-label="go home" href="/">
            <Image
              alt="Tuntun.In"
              className="h-8 w-auto"
              height={32}
              priority
              src="/logo/logo.png"
              width={157}
            />
          </Link>
          <h1 className="mt-4 mb-1 font-semibold text-xl">
            Create your Tuntun.In account
          </h1>
          <p className="text-sm">Join to start your journey</p>
        </div>

        <GoogleSignInButton callbackURL="/dashboard" />

        <div className="mt-6 flex flex-col gap-6">
          <form.Field name="name">
            {(field) => (
              <div className="flex flex-col gap-2">
                <Label className="block text-sm" htmlFor={field.name}>
                  Name
                </Label>
                <Input
                  id={field.name}
                  name={field.name}
                  onBlur={field.handleBlur}
                  onChange={(e) => field.handleChange(e.target.value)}
                  value={field.state.value}
                />
                {field.state.meta.errors.map((error) => (
                  <p className="text-destructive text-sm" key={error?.message}>
                    {error?.message}
                  </p>
                ))}
              </div>
            )}
          </form.Field>

          <form.Field name="email">
            {(field) => (
              <div className="flex flex-col gap-2">
                <Label className="block text-sm" htmlFor={field.name}>
                  Email
                </Label>
                <Input
                  id={field.name}
                  name={field.name}
                  onBlur={field.handleBlur}
                  onChange={(e) => field.handleChange(e.target.value)}
                  type="email"
                  value={field.state.value}
                />
                {field.state.meta.errors.map((error) => (
                  <p className="text-destructive text-sm" key={error?.message}>
                    {error?.message}
                  </p>
                ))}
              </div>
            )}
          </form.Field>

          <form.Field name="password">
            {(field) => (
              <div className="flex flex-col gap-2">
                <Label className="text-sm" htmlFor={field.name}>
                  Password
                </Label>
                <Input
                  id={field.name}
                  name={field.name}
                  onBlur={field.handleBlur}
                  onChange={(e) => field.handleChange(e.target.value)}
                  type="password"
                  value={field.state.value}
                />
                {field.state.meta.errors.map((error) => (
                  <p className="text-destructive text-sm" key={error?.message}>
                    {error?.message}
                  </p>
                ))}
              </div>
            )}
          </form.Field>

          <form.Subscribe
            selector={(state) => ({
              canSubmit: state.canSubmit,
              isSubmitting: state.isSubmitting,
            })}
          >
            {({ canSubmit, isSubmitting }) => (
              <Button
                className="w-full"
                disabled={!canSubmit || isSubmitting}
                type="submit"
              >
                {isSubmitting ? "Signing up..." : "Sign Up"}
              </Button>
            )}
          </form.Subscribe>
        </div>
      </div>

      <div className="rounded-(--radius) border bg-muted p-3">
        <p className="text-center text-accent-foreground text-sm">
          Already have an account?
          <Button asChild className="px-2" variant="link">
            <Link href="/login">Sign in</Link>
          </Button>
        </p>
      </div>
    </form>
  );
}
