"use client";

import { Separator } from "@tuntun-in/ui/components/separator";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@tuntun-in/ui/components/sidebar";
import { cn } from "@tuntun-in/ui/lib/utils";
import { LayoutDashboardIcon } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import UserMenu from "@/components/user-menu";

const navItems = [
  {
    icon: LayoutDashboardIcon,
    label: "Dashboard",
    href: "/dashboard",
  },
] as const;

export function DashboardSidebar() {
  const pathname = usePathname();

  return (
    <Sidebar>
      <SidebarHeader className="text-sidebar-accent-foreground">
        <Link className="flex items-center gap-2 px-2 pt-2" href="/dashboard">
          <div className="flex items-center justify-center gap-4">
            <Image
              alt="Tuntun.In"
              height={32}
              src="/logo/logo.png"
              width={157}
            />
          </div>
        </Link>
      </SidebarHeader>
      <div className="px-4 py-2">
        <Separator className="bg-[#5D6B68] opacity-40" />
      </div>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    className={cn(
                      "h-10 border border-transparent from-5% from-sidebar-accent via-30% via-sidebar/50 to-sidebar/50 transition-all duration-200 hover:border-black/40 hover:bg-linear-to-r/oklch",
                      pathname === item.href &&
                        "border-[#5D6B68]/10 bg-linear-to-r/oklch"
                    )}
                    isActive={pathname === item.href}
                  >
                    <Link href={item.href}>
                      <item.icon className="size-5" />
                      <span className="font-medium text-sm tracking-tight">
                        {item.label}
                      </span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <UserMenu />
      </SidebarFooter>
    </Sidebar>
  );
}
