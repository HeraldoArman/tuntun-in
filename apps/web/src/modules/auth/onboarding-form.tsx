"use client";

import { useForm } from "@tanstack/react-form";
import { api } from "@tuntun-in/backend/convex/_generated/api";
import { Button } from "@tuntun-in/ui/components/button";
import { Input } from "@tuntun-in/ui/components/input";
import { Label } from "@tuntun-in/ui/components/label";
import {
  RadioGroup,
  RadioGroupItem,
} from "@tuntun-in/ui/components/radio-group";
import { useMutation } from "convex/react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import z from "zod";

export function OnboardingForm({ authName }: { authName: string }) {
  const router = useRouter();
  const createUserProfile = useMutation(api.userProfiles.create);

  const form = useForm({
    defaultValues: {
      fullName: "",
      role: "blind_user" as "blind_user" | "guardian",
      whatsappNumber: "",
    },
    onSubmit: async ({ value }) => {
      try {
        await createUserProfile({
          role: value.role,
          fullName: value.fullName,
          whatsappNumber:
            value.role === "guardian" ? value.whatsappNumber : undefined,
        });
        router.push("/dashboard");
        toast.success("Profile created successfully");
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : "Failed to create profile"
        );
      }
    },
    validators: {
      onSubmit: z.object({
        fullName: z.string().min(2, "Name must be at least 2 characters"),
        role: z.union([z.literal("blind_user"), z.literal("guardian")]),
        whatsappNumber: z.string(),
      }),
    },
  });

  // Pre-fill name from auth user
  const authNamePlaceholder = authName || "Enter your full name";

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
            Complete your profile
          </h1>
          <p className="text-sm">Tell us how you&apos;ll be using Tuntun.In</p>
        </div>

        <div className="mt-6 flex flex-col gap-6">
          <form.Field name="fullName">
            {(field) => (
              <div className="flex flex-col gap-2">
                <Label className="block text-sm" htmlFor={field.name}>
                  Full Name
                </Label>
                <Input
                  id={field.name}
                  name={field.name}
                  onBlur={field.handleBlur}
                  onChange={(e) => field.handleChange(e.target.value)}
                  placeholder={authNamePlaceholder}
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

          <form.Field name="role">
            {(field) => (
              <div className="flex flex-col gap-2">
                <Label className="text-sm">I am registering as</Label>
                <RadioGroup
                  onValueChange={(value) =>
                    field.handleChange(value as "blind_user" | "guardian")
                  }
                  value={field.state.value}
                >
                  <div className="flex items-center gap-2">
                    <RadioGroupItem id="role-blind" value="blind_user" />
                    <Label className="text-sm" htmlFor="role-blind">
                      Visually impaired user
                    </Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <RadioGroupItem id="role-guardian" value="guardian" />
                    <Label className="text-sm" htmlFor="role-guardian">
                      Guardian / family member
                    </Label>
                  </div>
                </RadioGroup>
                {field.state.meta.errors.map((error) => (
                  <p className="text-destructive text-sm" key={error?.message}>
                    {error?.message}
                  </p>
                ))}
              </div>
            )}
          </form.Field>

          <form.Subscribe selector={(state) => state.values.role}>
            {(role) =>
              role === "guardian" && (
                <form.Field name="whatsappNumber">
                  {(field) => (
                    <div className="flex flex-col gap-2">
                      <Label className="text-sm" htmlFor={field.name}>
                        WhatsApp Number
                      </Label>
                      <Input
                        id={field.name}
                        name={field.name}
                        onBlur={field.handleBlur}
                        onChange={(e) => field.handleChange(e.target.value)}
                        placeholder="+62 812 3456 7890"
                        type="tel"
                        value={field.state.value}
                      />
                      <p className="text-muted-foreground text-sm">
                        Used to send you Overwatch alerts when your loved one
                        needs help.
                      </p>
                      {field.state.meta.errors.map((error) => (
                        <p
                          className="text-destructive text-sm"
                          key={error?.message}
                        >
                          {error?.message}
                        </p>
                      ))}
                    </div>
                  )}
                </form.Field>
              )
            }
          </form.Subscribe>

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
                {isSubmitting ? "Saving..." : "Complete Profile"}
              </Button>
            )}
          </form.Subscribe>
        </div>
      </div>
    </form>
  );
}
