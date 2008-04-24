import wizard
import time
import datetime
import pooler
import base64

form = """<?xml version="1.0"?>
<form string="Select Fiscal Year">
    <label string="This wizard will create an XML file for Vat details and total invoiced amounts per human entity(Partner)."  colspan="4"/>
    <newline/>
    <field name="fyear" />
    <newline/>
    <field name="mand_id" />
</form>"""

fields = {
    'fyear': {'string': 'Fiscal Year', 'type': 'many2one', 'relation': 'account.fiscalyear', 'required': True,},
    'mand_id':{'string':'MandatarieId','type':'char','size':'30','required': True,},
   }
msg_form = """<?xml version="1.0"?>
<form string="Notification">
     <separator string="XML File has been Created."  colspan="4"/>
     <field name="msg" colspan="4" nolabel="1"/>
     <field name="file_save" />
</form>"""

msg_fields = {
  'msg': {'string':'File created', 'type':'text', 'size':'100','readonly':True},
  'file_save':{'string': 'Save File',
        'type': 'binary',
        'readonly': True,},
}

class wizard_vat(wizard.interface):

    def _create_xml(self, cr, uid, data, context):

        datas=[]
        obj_company=pooler.get_pool(cr.dbname).get('res.company').browse(cr,uid,1)
        vat_company=obj_company.partner_id.vat
        if not vat_company:
            raise wizard.except_wizard('Data Insufficient','No VAT Number Associated with Main Company!')

        p_id_list=pooler.get_pool(cr.dbname).get('res.partner').search(cr,uid,[('vat','!=',False)])

        if not p_id_list:
             raise wizard.except_wizard('Data Insufficient!','No partner has a VAT Number asociated with him.')
        obj_year=pooler.get_pool(cr.dbname).get('account.fiscalyear').browse(cr,uid,data['form']['fyear'])
        period="to_date('" + str(obj_year.date_start) + "','yyyy-mm-dd') and to_date('" + str(obj_year.date_stop) +"','yyyy-mm-dd')"

        street=zip_city=country=''
        if not obj_company.partner_id.address:
                street=zip_city=country=''

        for ads in obj_company.partner_id.address:
                if ads.type=='default':
                    if ads.zip_id:
                        zip_city=pooler.get_pool(cr.dbname).get('res.partner.zip').name_get(cr,uid,[ads.zip_id.id])[0][1]
                    if ads.street:
                        street=ads.street
                    if ads.street2:
                        street +=ads.street2
                    if ads.country_id:
                        country=ads.country_id.code

        sender_date=time.strftime('%Y-%m-%d')
        data_file='<?xml version="1.0"?>\n<VatList xmlns="http://www.minfin.fgov.be/VatList" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.minfin.fgov.be/VatList VatList.xml" RecipientId="VAT-ADMIN" SenderId="'+ str(vat_company) + '"'
        data_file +=' ControlRef="" MandataireId="'+ data['form']['mand_id'] + '" SenderDate="'+ str(sender_date)+'" VersionTech="1.2">'
        data_file +='\n<AgentRepr DecNumber="1">\n\t<CompanyInfo>\n\t\t<VATNum>'+str(vat_company)+'</VATNum>\n\t\t<Name>'+str(obj_company.name)+'</Name>\n\t\t<Street>'+ str(street) +'</Street>\n\t\t<CityAndZipCode>'+ str(zip_city) +'</CityAndZipCode>'
        data_file +='\n\t\t<Country>'+ str(country) +'</Country>\n\t</CompanyInfo>\n</AgentRepr>'
        data_comp ='\n<CompanyInfo>\n\t<VATNum>'+str(vat_company)+'</VATNum>\n\t<Name>'+str(obj_company.name)+'</Name>\n\t<Street>'+ str(street) +'</Street>\n\t<CityAndZipCode>'+ str(zip_city) +'</CityAndZipCode>\n\t<Country>'+ str(country) +'</Country>\n</CompanyInfo>'
        data_period ='\n<Period>'+ str(obj_year.name[-4:]) +'</Period>'

        for p_id in p_id_list:
            record=[] # this holds record per partner
            obj_partner=pooler.get_pool(cr.dbname).get('res.partner').browse(cr,uid,p_id)


            cr.execute('select a.type,sum(credit)-sum(debit) from account_move_line l left join account_account a on (l.account_id=a.id) where a.type in ('"'income'"','"'tax'"') and l.partner_id=%d and l.date between %s group by a.type'%(p_id,period))
            line_info=cr.fetchall()

            if not line_info:
                continue

            record.append(obj_partner.vat)
            for ads in obj_partner.address:
                if ads.type=='default':
                    if ads.country_id:
                        record.append(ads.country_id.code)
                    else:
                        raise wizard.except_wizard('Data Insufficient!', 'The Partner "'+obj_partner.name + '"'' has no country associated with its default type address!')
                else:
                    raise wizard.except_wizard('Data Insufficient!', 'The Partner "'+obj_partner.name + '"'' has no default type address!')
            if len(line_info)==1:
                if line_info[0][0]=='income':
                       record.append(0.00)
                       record.append(line_info[0][1])
                else:
                       record.append(line_info[0][1])
                       record.append(0.00)
            else:
                for item in line_info:
                    record.append(item[1])
            datas.append(record)

        seq=0
        data_clientinfo=''
        sum_tax=0.00
        sum_turnover=0.00
        for line in datas:
            if line[3]< 250.00:
                continue
            seq +=1
            sum_tax +=line[2]
            sum_turnover +=line[3]
            data_clientinfo +='\n<ClientList SequenceNum="'+str(seq)+'">\n\t<CompanyInfo>\n\t\t<VATNum>'+line[0] +'</VATNum>\n\t\t<Country>'+line[1] +'</Country>\n\t</CompanyInfo>\n\t<Amount>'+str(int(line[2] * 100)) +'</Amount>\n\t<TurnOver>'+str(int(line[3] * 100)) +'</TurnOver>\n</ClientList>\n'

        data_decl ='\n<DeclarantList SequenceNum="1" DeclarantNum="" ClientNbr="'+ str(seq) +'" TurnOverSum="'+ str(int(sum_turnover * 100)) +'" TaxSum="'+ str(int(sum_tax * 100)) +'" />'
        data_file += str(data_decl) + str(data_comp) + str(data_period) + str(data_clientinfo) + '</VatList>'

        data['form']['msg']='Save the File with '".xml"' extension.'
        data['form']['file_save']=base64.encodestring(data_file)
        return data['form']

    states = {
        'init': {
            'actions': [],
            'result': {'type':'form', 'arch':form, 'fields':fields, 'state':[('end','Cancel'),('go','Create XML')]},
        },
        'go': {
            'actions': [_create_xml],
            'result': {'type':'form', 'arch':msg_form, 'fields':msg_fields, 'state':[('end','Ok')]},
        }

    }

wizard_vat('list.vat.detail')
