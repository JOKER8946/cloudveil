// CloudVeil NS-3 evaluation scenario.
//
// Models the WAN path between a CloudVeil client and an Azure region (and,
// with --regions=2, the primary->secondary replication hop). A TCP bulk
// transfer of a configurable payload is sent across point-to-point links whose
// delay, bandwidth and packet-loss are swept by run_all.sh. FlowMonitor
// measures throughput, mean latency and packet loss; one CSV row is appended
// per run.
//
// Build: place in the ns-3 `scratch/` directory and `./ns3 build`.
// Run:   ./ns3 run "cloudveil_sim --delay=50 --rate=20 --loss=1 \
//            --payload=1048576 --regions=1 --label=wan --out=results.csv"

#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"
#include "ns3/point-to-point-module.h"

#include <fstream>
#include <sys/stat.h>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("CloudVeilSim");

int
main(int argc, char* argv[])
{
    uint32_t regions = 1;      // 1 = two-node WAN; 2 = multi-region (replication)
    double delayMs = 50.0;     // one-way link delay (20..300)
    double rateMbps = 20.0;    // link bandwidth (1..100)
    double lossPct = 0.0;      // packet loss percentage (0..5)
    uint32_t payload = 1048576; // bytes to transfer
    std::string label = "wan";
    std::string outFile = "cloudveil_results.csv";

    CommandLine cmd(__FILE__);
    cmd.AddValue("regions", "Number of region hops (1=WAN, 2=multi-region)", regions);
    cmd.AddValue("delay", "One-way link delay in ms", delayMs);
    cmd.AddValue("rate", "Link bandwidth in Mbps", rateMbps);
    cmd.AddValue("loss", "Packet loss percentage", lossPct);
    cmd.AddValue("payload", "Payload size in bytes", payload);
    cmd.AddValue("label", "Scenario label", label);
    cmd.AddValue("out", "CSV output file", outFile);
    cmd.Parse(argc, argv);

    uint32_t nNodes = regions + 1;
    NodeContainer nodes;
    nodes.Create(nNodes);

    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue(std::to_string(rateMbps) + "Mbps"));
    p2p.SetChannelAttribute("Delay", StringValue(std::to_string(delayMs) + "ms"));

    InternetStackHelper stack;
    stack.Install(nodes);

    Ipv4AddressHelper addr;
    Ipv4InterfaceContainer lastIf;
    for (uint32_t i = 0; i + 1 < nNodes; ++i)
    {
        NetDeviceContainer dev = p2p.Install(nodes.Get(i), nodes.Get(i + 1));
        if (lossPct > 0.0)
        {
            Ptr<RateErrorModel> em = CreateObject<RateErrorModel>();
            em->SetAttribute("ErrorRate", DoubleValue(lossPct / 100.0));
            em->SetUnit(RateErrorModel::ERROR_UNIT_PACKET);
            dev.Get(1)->SetAttribute("ReceiveErrorModel", PointerValue(em));
        }
        std::ostringstream base;
        base << "10.1." << (i + 1) << ".0";
        addr.SetBase(base.str().c_str(), "255.255.255.0");
        lastIf = addr.Assign(dev);
    }
    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    uint16_t port = 9;
    Address sinkAddress(InetSocketAddress(lastIf.GetAddress(1), port));
    PacketSinkHelper sink("ns3::TcpSocketFactory",
                          InetSocketAddress(Ipv4Address::GetAny(), port));
    ApplicationContainer sinkApp = sink.Install(nodes.Get(nNodes - 1));
    sinkApp.Start(Seconds(0.0));
    sinkApp.Stop(Seconds(120.0));

    BulkSendHelper source("ns3::TcpSocketFactory", sinkAddress);
    source.SetAttribute("MaxBytes", UintegerValue(payload));
    ApplicationContainer sourceApp = source.Install(nodes.Get(0));
    sourceApp.Start(Seconds(1.0));
    sourceApp.Stop(Seconds(120.0));

    FlowMonitorHelper fmHelper;
    Ptr<FlowMonitor> monitor = fmHelper.InstallAll();

    Simulator::Stop(Seconds(121.0));
    Simulator::Run();
    monitor->CheckForLostPackets();

    double throughputMbps = 0.0;
    double meanDelayMs = 0.0;
    uint64_t rxPackets = 0;
    uint64_t txPackets = 0;
    uint64_t lostPackets = 0;
    uint64_t rxBytes = 0;

    for (auto& kv : monitor->GetFlowStats())
    {
        const FlowMonitor::FlowStats& st = kv.second;
        // Forward (data) flow carries the bulk of the bytes.
        if (st.rxBytes > rxBytes)
        {
            rxBytes = st.rxBytes;
            rxPackets = st.rxPackets;
            txPackets = st.txPackets;
            lostPackets = st.lostPackets;
            double span = (st.timeLastRxPacket - st.timeFirstTxPacket).GetSeconds();
            if (span > 0)
            {
                throughputMbps = (st.rxBytes * 8.0) / span / 1e6;
            }
            if (st.rxPackets > 0)
            {
                meanDelayMs = (st.delaySum.GetSeconds() / st.rxPackets) * 1000.0;
            }
        }
    }

    double lossMeasured =
        txPackets > 0 ? (100.0 * static_cast<double>(lostPackets) / txPackets) : 0.0;

    struct stat buffer;
    bool newFile = (stat(outFile.c_str(), &buffer) != 0);
    std::ofstream out(outFile, std::ios::app);
    if (newFile)
    {
        out << "label,regions,delay_ms,rate_mbps,loss_pct,payload_bytes,"
               "throughput_mbps,mean_delay_ms,loss_measured_pct,rx_packets,tx_packets\n";
    }
    out << label << "," << regions << "," << delayMs << "," << rateMbps << ","
        << lossPct << "," << payload << "," << throughputMbps << "," << meanDelayMs
        << "," << lossMeasured << "," << rxPackets << "," << txPackets << "\n";
    out.close();

    std::cout << "[" << label << "] regions=" << regions << " delay=" << delayMs
              << "ms rate=" << rateMbps << "Mbps loss=" << lossPct
              << "% -> throughput=" << throughputMbps << "Mbps delay=" << meanDelayMs
              << "ms loss=" << lossMeasured << "%\n";

    Simulator::Destroy();
    return 0;
}
