import ScannerView from '../ScannerView'
import PageHeader from '../components/PageHeader'

export default function ScannerPage() {
  return (
    <>
      <PageHeader
        kicker="MARKET DISCOVERY"
        title="Equity scanner"
        subtitle="Scan NIFTY 50 stocks for technical conditions."
      />
      <ScannerView />
    </>
  )
}
