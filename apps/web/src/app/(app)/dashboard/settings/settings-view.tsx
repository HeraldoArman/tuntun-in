"use client";

import { usePreloadedAuthQuery } from "@convex-dev/better-auth/nextjs/client";
import { useForm } from "@tanstack/react-form";
import { api } from "@tuntun-in/backend/convex/_generated/api";
import { Badge } from "@tuntun-in/ui/components/badge";
import { Button } from "@tuntun-in/ui/components/button";
import { Input } from "@tuntun-in/ui/components/input";
import { Label } from "@tuntun-in/ui/components/label";
import type { Preloaded } from "convex/react";
import { useMutation } from "convex/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";
import z from "zod";

import { PageLoader } from "@/components/page-loader";

export function SettingsView({
  preloadedUser,
  preloadedProfile,
}: {
  preloadedUser: Preloaded<typeof api.auth.getCurrentUser>;
  preloadedProfile: Preloaded<typeof api.userProfiles.getCurrent>;
}) {
  const router = useRouter();
  const user = usePreloadedAuthQuery(preloadedUser);
  const profile = usePreloadedAuthQuery(preloadedProfile);
  const updateProfile = useMutation(api.userProfiles.update);

  useEffect(() => {
    if (user === null) {
      router.replace("/login" as never);
    }
  }, [user, router]);

  useEffect(() => {
    if (profile !== undefined && profile === null) {
      router.replace("/onboarding" as never);
    }
  }, [profile, router]);

  const isGuardian = profile?.role === "guardian";

  const form = useForm({
    defaultValues: {
      fullName: profile?.fullName ?? "",
      whatsappNumber: profile?.whatsappNumber ?? "",
    },
    onSubmit: async ({ value }) => {
      try {
        await updateProfile({
          fullName: value.fullName,
          whatsappNumber: isGuardian ? value.whatsappNumber : undefined,
        });
        toast.success("Settings saved");
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : "Failed to save settings"
        );
      }
    },
    validators: {
      onSubmit: z.object({
        fullName: z.string().min(2, "Name must be at least 2 characters"),
        whatsappNumber: z.string(),
      }),
    },
  });

  if (
    user === null ||
    profile === null ||
    user === undefined ||
    profile === undefined
  ) {
    return <PageLoader />;
  }

  return (
    <div className="p-6">
      <div className="mb-8">
        <h1 className="font-semibold text-2xl">Settings</h1>
        <p className="mt-1 text-muted-foreground text-sm">
          Update your profile information and account preferences
        </p>
      </div>

      <div className="flex max-w-2xl flex-col gap-8">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            e.stopPropagation();
            form.handleSubmit();
          }}
        >
          <div className="flex flex-col gap-6">
            <div className="rounded-xl border bg-card p-6 shadow-sm">
              <div className="mb-6">
                <h2 className="font-semibold text-lg">Profile</h2>
                <p className="text-muted-foreground text-sm">
                  Update your personal information
                </p>
              </div>

              <div className="flex flex-col gap-6">
                <form.Field name="fullName">
                  {(field) => (
                    <div className="flex flex-col gap-2">
                      <Label className="text-sm" htmlFor={field.name}>
                        Full Name
                      </Label>
                      <Input
                        id={field.name}
                        name={field.name}
                        onBlur={field.handleBlur}
                        onChange={(e) => field.handleChange(e.target.value)}
                        value={field.state.value}
                      />
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

                {isGuardian && (
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
                        <div className="rounded-md bg-muted p-3">
                          <p className="text-muted-foreground text-sm">
                            Used to send you Overwatch alerts when the user
                            needs assistance.
                          </p>
                        </div>
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
                )}
              </div>

              <div className="mt-6 flex justify-end">
                <form.Subscribe
                  selector={(state) => ({
                    canSubmit: state.canSubmit,
                    isSubmitting: state.isSubmitting,
                  })}
                >
                  {({ canSubmit, isSubmitting }) => (
                    <Button
                      className="min-w-[120px]"
                      disabled={!canSubmit || isSubmitting}
                      type="submit"
                    >
                      {isSubmitting ? "Saving..." : "Save Changes"}
                    </Button>
                  )}
                </form.Subscribe>
              </div>
            </div>

            <div className="rounded-xl border bg-card p-6 shadow-sm">
              <div className="mb-6">
                <h2 className="font-semibold text-lg">Account</h2>
                <p className="text-muted-foreground text-sm">
                  Read-only account information
                </p>
              </div>

              <div className="flex flex-col gap-6">
                <div className="flex flex-col gap-2">
                  <Label className="text-sm">Email</Label>
                  <Input className="bg-muted/50" disabled value={user.email} />
                  <p className="text-muted-foreground text-xs">
                    Email cannot be changed. Contact support if you need to
                    update it.
                  </p>
                </div>

                <div className="flex flex-col gap-2">
                  <Label className="text-sm">Role</Label>
                  <div className="flex items-center gap-3">
                    <Badge
                      className="px-3 py-1 text-sm"
                      variant={isGuardian ? "default" : "secondary"}
                    >
                      {isGuardian ? "Guardian" : "Blind User"}
                    </Badge>
                  </div>
                  <p className="text-muted-foreground text-xs">
                    Role is set during onboarding and cannot be changed
                  </p>
                </div>
              </div>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
