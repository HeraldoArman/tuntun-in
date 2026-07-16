"use client";

import { useForm } from "@tanstack/react-form";
import { api } from "@tuntun-in/backend/convex/_generated/api";
import { Badge } from "@tuntun-in/ui/components/badge";
import { Button } from "@tuntun-in/ui/components/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@tuntun-in/ui/components/card";
import { Input } from "@tuntun-in/ui/components/input";
import { Label } from "@tuntun-in/ui/components/label";
import { useMutation, useQuery } from "convex/react";
import { ShieldIcon, Trash2Icon, UserPlusIcon } from "lucide-react";
import { toast } from "sonner";
import z from "zod";

function renderBlindUserList(
  blindUsers:
    | {
        _id: string;
        fullName: string;
        email?: string;
      }[]
    | undefined,
  onRemove: (id: string) => void
) {
  if (blindUsers === undefined) {
    return <p className="text-muted-foreground text-sm">Loading...</p>;
  }
  if (blindUsers.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No blind users linked yet. Add one above to get started.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-3">
      {blindUsers.map((blindUser) => (
        <li
          className="flex items-center justify-between rounded-lg border p-3"
          key={blindUser._id}
        >
          <div className="flex flex-col gap-0.5">
            <span className="font-medium text-sm">{blindUser.fullName}</span>
            {blindUser.email && (
              <span className="text-muted-foreground text-xs">
                {blindUser.email}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="secondary">Blind User</Badge>
            <Button
              onClick={() => onRemove(blindUser._id)}
              size="icon-sm"
              variant="ghost"
            >
              <Trash2Icon className="size-4 text-destructive" />
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function GuardianView() {
  const blindUsers = useQuery(api.guardianLinks.getMyBlindUsers);
  const addBlindUser = useMutation(api.guardianLinks.addBlindUser);
  const removeBlindUser = useMutation(api.guardianLinks.removeBlindUser);

  const form = useForm({
    defaultValues: { email: "" },
    onSubmit: async ({ value }) => {
      try {
        await addBlindUser({ blindUserEmail: value.email });
        form.reset();
        toast.success("Blind user linked successfully");
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : "Failed to link user"
        );
      }
    },
    validators: {
      onSubmit: z.object({
        email: z.string().email("Enter a valid email address"),
      }),
    },
  });

  const handleRemove = async (blindUserProfileId: string) => {
    try {
      await removeBlindUser({
        blindUserProfileId: blindUserProfileId as never,
      });
      toast.success("User removed");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to remove user"
      );
    }
  };

  return (
    <div className="p-6">
      <div className="mb-8">
        <h1 className="font-semibold text-2xl">Guardian</h1>
        <p className="mt-1 text-muted-foreground text-sm">
          Add and manage the blind users you watch over.
        </p>
      </div>

      <div className="flex max-w-2xl flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <UserPlusIcon className="size-5" />
              Add Blind User
            </CardTitle>
            <CardDescription>
              Enter the email of a registered blind user to link them to your
              account.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                e.stopPropagation();
                form.handleSubmit();
              }}
            >
              <div className="flex flex-col gap-4">
                <form.Field name="email">
                  {(field) => (
                    <div className="flex flex-col gap-2">
                      <Label className="text-sm" htmlFor={field.name}>
                        Blind User Email
                      </Label>
                      <Input
                        id={field.name}
                        name={field.name}
                        onBlur={field.handleBlur}
                        onChange={(e) => field.handleChange(e.target.value)}
                        placeholder="blinduser@example.com"
                        type="email"
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
                <form.Subscribe
                  selector={(state) => ({
                    canSubmit: state.canSubmit,
                    isSubmitting: state.isSubmitting,
                  })}
                >
                  {({ canSubmit, isSubmitting }) => (
                    <Button
                      className="w-fit"
                      disabled={!canSubmit || isSubmitting}
                      type="submit"
                    >
                      {isSubmitting ? "Linking..." : "Link User"}
                    </Button>
                  )}
                </form.Subscribe>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <ShieldIcon className="size-5" />
              Linked Blind Users
            </CardTitle>
            <CardDescription>
              Users you can monitor and receive Overwatch alerts for.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {renderBlindUserList(blindUsers, handleRemove)}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
