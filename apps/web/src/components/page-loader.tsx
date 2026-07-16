import { Loader2Icon } from "lucide-react";

export function PageLoader({
  title = "Loading...",
  description = "Please wait while we prepare your page.",
}: {
  title?: string;
  description?: string;
}) {
  return (
    <div className="flex min-h-screen flex-1 items-center justify-center px-4 py-16">
      <div className="flex flex-col items-center justify-center gap-y-6 rounded-lg bg-background p-10 shadow-sm">
        <Loader2Icon className="size-6 animate-spin text-primary" />
        <div className="flex flex-col gap-y-2 text-center">
          <h6 className="font-medium text-lg">{title}</h6>
          <p className="text-muted-foreground text-sm">{description}</p>
        </div>
      </div>
    </div>
  );
}
