import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'

export function FaqBlock({ items }: { items: { q: string; a: string }[] }) {
  return (
    <Accordion className="rounded-md border border-border px-2.5">
      {items.map((item, i) => (
        <AccordionItem key={i} value={`faq-${i}`}>
          <AccordionTrigger className="py-1.5 text-[13px] font-medium">{item.q}</AccordionTrigger>
          <AccordionContent>
            <p className="text-[13px] leading-relaxed text-muted-foreground">{item.a}</p>
          </AccordionContent>
        </AccordionItem>
      ))}
    </Accordion>
  )
}
