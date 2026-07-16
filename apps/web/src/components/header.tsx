"use client";

import { Button } from "@tuntun-in/ui/components/button";
import { Skeleton } from "@tuntun-in/ui/components/skeleton";
import { cn } from "@tuntun-in/ui/lib/utils";
import { Authenticated, AuthLoading, Unauthenticated } from "convex/react";
import { Menu, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import UserMenu from "./user-menu";

const landingMenuItems = [
  { name: "Features", href: "/#features" },
  { name: "How It Works", href: "/#how-it-works" },
] as const;

export default function Header() {
  const [menuState, setMenuState] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 50);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <header>
      <nav
        className="fixed z-20 w-full px-2"
        data-state={menuState && "active"}
      >
        <div
          className={cn(
            "mx-auto mt-2 max-w-6xl px-6 transition-all duration-300 lg:px-12",
            isScrolled &&
              "max-w-4xl rounded-2xl border bg-background/50 backdrop-blur-lg lg:px-5"
          )}
        >
          <div className="relative flex flex-wrap items-center justify-between gap-6 py-3 lg:gap-0 lg:py-4">
            <div className="flex w-full justify-between lg:w-auto">
              <Link
                aria-label="Tuntun.In home"
                className="flex items-center"
                href="/"
              >
                <Image
                  alt="Tuntun.In"
                  className="h-8 w-auto"
                  height={32}
                  priority
                  src="/logo/logo.png"
                  width={157}
                />
              </Link>

              <button
                aria-label={menuState ? "Close Menu" : "Open Menu"}
                className="relative z-20 -m-2.5 -mr-4 block cursor-pointer p-2.5 lg:hidden"
                onClick={() => setMenuState(!menuState)}
                type="button"
              >
                <Menu className="m-auto size-6 in-data-[state=active]:rotate-180 in-data-[state=active]:scale-0 in-data-[state=active]:opacity-0 duration-200" />
                <X className="absolute inset-0 m-auto size-6 -rotate-180 in-data-[state=active]:rotate-0 in-data-[state=active]:scale-100 scale-0 in-data-[state=active]:opacity-100 opacity-0 duration-200" />
              </button>
            </div>

            <div className="absolute inset-0 m-auto hidden size-fit lg:block">
              {pathname === "/" && (
                <ul className="flex gap-8 text-sm">
                  {landingMenuItems.map((item) => {
                    const isActive = item.href.startsWith("/#");
                    return (
                      <li key={item.href}>
                        <Link
                          className={cn(
                            "block text-muted-foreground duration-150 hover:text-accent-foreground",
                            isActive && "text-foreground"
                          )}
                          href={item.href}
                        >
                          <span>{item.name}</span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            <div className="mb-6 in-data-[state=active]:block hidden w-full flex-wrap items-center justify-end space-y-8 rounded-3xl border bg-background p-6 shadow-2xl shadow-zinc-300/20 md:flex-nowrap lg:m-0 lg:flex lg:in-data-[state=active]:flex lg:w-fit lg:gap-6 lg:space-y-0 lg:border-transparent lg:bg-transparent lg:p-0 lg:shadow-none dark:shadow-none dark:lg:bg-transparent">
              <div className="lg:hidden">
                {pathname === "/" && (
                  <ul className="space-y-6 text-base">
                    {landingMenuItems.map((item) => (
                      <li key={item.href}>
                        <Link
                          className="block text-muted-foreground duration-150 hover:text-accent-foreground"
                          href={item.href}
                        >
                          <span>{item.name}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="flex w-full flex-col gap-3 sm:flex-row sm:gap-3 md:w-fit">
                <AuthLoading>
                  <Skeleton className="h-9 w-20" />
                </AuthLoading>
                <Authenticated>
                  <Button asChild size="sm" variant="outline">
                    <Link href="/dashboard">
                      <span>Dashboard</span>
                    </Link>
                  </Button>
                  <UserMenu />
                </Authenticated>
                <Unauthenticated>
                  <Button
                    asChild
                    className={cn(isScrolled && "lg:hidden")}
                    size="sm"
                    variant="outline"
                  >
                    <Link href="/login">
                      <span>Login</span>
                    </Link>
                  </Button>
                  <Button
                    asChild
                    className={cn(isScrolled && "lg:hidden")}
                    size="sm"
                  >
                    <Link href="/register">
                      <span>Sign Up</span>
                    </Link>
                  </Button>
                  <Button
                    asChild
                    className={cn(isScrolled ? "lg:inline-flex" : "hidden")}
                    size="sm"
                  >
                    <Link href="/register">
                      <span>Get Started</span>
                    </Link>
                  </Button>
                </Unauthenticated>
              </div>
            </div>
          </div>
        </div>
      </nav>
    </header>
  );
}
