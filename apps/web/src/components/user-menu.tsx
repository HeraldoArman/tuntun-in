"use client";

import { api } from "@tuntun-in/backend/convex/_generated/api";
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from "@tuntun-in/ui/components/avatar";
import { Button } from "@tuntun-in/ui/components/button";
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@tuntun-in/ui/components/drawer";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@tuntun-in/ui/components/dropdown-menu";
import { useIsMobile } from "@tuntun-in/ui/hooks/use-mobile";
import { useQuery } from "convex/react";
import { ChevronDownIcon, LogOutIcon, SettingsIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { authClient } from "@/lib/auth-client";

const roleLabels: Record<string, string> = {
  blind_user: "Blind User",
  guardian: "Guardian",
};

export default function UserMenu() {
  const router = useRouter();
  const { data, isPending } = authClient.useSession();
  const profile = useQuery(api.userProfiles.getCurrent);
  const isMobile = useIsMobile();

  const onLogout = () => {
    authClient.signOut({
      fetchOptions: {
        onSuccess: () => {
          router.push("/login");
        },
      },
    });
  };

  const roleLabel = profile ? roleLabels[profile.role] : undefined;

  if (isPending || !data?.user) {
    return null;
  }

  const { name, email, image } = data.user;
  const initials = name
    ?.split(" ")
    .map((part) => part[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  if (isMobile) {
    return (
      <Drawer>
        <DrawerTrigger className="flex w-full items-center justify-between gap-x-2 overflow-hidden rounded-lg border border-border/10 bg-white/5 p-3 hover:bg-white/10">
          {image ? (
            <Avatar>
              <AvatarImage src={image} />
            </Avatar>
          ) : (
            <Avatar>
              <AvatarFallback className="font-medium text-sm">
                {initials}
              </AvatarFallback>
            </Avatar>
          )}
          <div className="flex min-w-0 flex-1 flex-col gap-0.5 overflow-hidden text-left">
            <p className="w-full truncate text-sm">{name}</p>
            <p className="w-full truncate text-muted-foreground text-xs">
              {roleLabel ?? email}
            </p>
          </div>
          <ChevronDownIcon className="size-4 shrink-0" />
        </DrawerTrigger>
        <DrawerContent>
          <DrawerHeader>
            <DrawerTitle>{name}</DrawerTitle>
            <DrawerDescription>
              {roleLabel ? `${roleLabel} · ${email}` : email}
            </DrawerDescription>
          </DrawerHeader>
          <DrawerFooter>
            <Button asChild variant="outline">
              <Link href="/dashboard/settings">
                <SettingsIcon className="size-4" />
                Settings
              </Link>
            </Button>
            <Button onClick={onLogout} variant="outline">
              <LogOutIcon className="size-4" />
              Logout
            </Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex w-full cursor-pointer items-center justify-between gap-x-2 overflow-hidden rounded-lg border border-border/10 bg-white/5 p-3 duration-200 hover:bg-black/10">
        {image ? (
          <Avatar>
            <AvatarImage src={image} />
          </Avatar>
        ) : (
          <Avatar>
            <AvatarFallback className="font-medium text-sm">
              {initials}
            </AvatarFallback>
          </Avatar>
        )}
        <div className="flex min-w-0 flex-1 flex-col gap-0.5 overflow-hidden text-left">
          <p className="w-full truncate text-sm">{name}</p>
          <p className="w-full truncate text-muted-foreground text-xs">
            {roleLabel ?? email}
          </p>
        </div>
        <ChevronDownIcon className="size-4 shrink-0" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72" side="right">
        <DropdownMenuLabel>
          <div className="flex flex-col gap-1">
            <span className="truncate font-medium">{name}</span>
            <span className="truncate font-normal text-muted-foreground text-sm">
              {roleLabel ? `${roleLabel} · ${email}` : email}
            </span>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="flex cursor-pointer items-center justify-between"
          onClick={() => router.push("/dashboard/settings" as never)}
        >
          Settings
          <SettingsIcon className="size-4" />
        </DropdownMenuItem>
        <DropdownMenuItem
          className="flex cursor-pointer items-center justify-between"
          onClick={onLogout}
        >
          Logout
          <LogOutIcon className="size-4" />
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
